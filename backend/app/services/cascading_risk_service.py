from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import (
    CascadeAnalysisRun,
    CascadePath,
    ComplexDataLink,
    FloodSpatialFeature,
    HistoricalFloodFeature,
    RainPumpProximityFeature,
    SeoulComplexProfile,
    StressTestRun,
    TerrainFeature,
)
from backend.app.services.seoul_resilience_service import latest_assessments

METHOD_TYPE = "evidence_graph"
METHOD_VERSION = "cascade-v1"
LABELS = {
    "HEAVY_RAIN":"집중강우", "SEWER_STRESS":"하수 배수부담", "RIVER_STRESS":"하천 수위부담",
    "LOWLAND_EXPOSURE":"저지대 노출", "HISTORICAL_FLOOD_EXPOSURE":"과거 침수노출",
    "EXPECTED_FLOOD_EXPOSURE":"침수예상구역 노출", "DRAINAGE_LIMITATION":"배수 인프라 접근성 제한",
    "COMPOUND_HYDROLOGIC_STRESS":"복합 수문 스트레스", "FLOOD_EXPOSURE":"침수 노출 경로",
    "ELEVATOR_SERVICE_IMPACT":"승강기 관련 설비 영향 점검", "UNDERGROUND_EQUIPMENT_REVIEW":"지하 전기·기계설비 확인",
    "ACCESS_FUNCTION_REVIEW":"지하 접근·주차 기능 확인", "FUNCTIONAL_DISRUPTION":"시설 기능영향 점검 경로",
    "RESILIENCE_DEGRADATION":"회복력 저하 경로",
}

def _e(dataset: str, feature: str, value: Any, unit: str | None = None) -> dict:
    item = {"dataset": dataset, "feature": feature, "value": value}
    if unit: item["unit"] = unit
    return item

def _node(node_id: str, status: str = "INACTIVE", severity: str = "NONE",
          evidence: list | None = None, missing: list | None = None) -> dict:
    return {"node_id":node_id,"label":LABELS[node_id],"status":status,"severity":severity,
            "evidence":evidence or [],"missing_evidence":missing or [],"method_version":METHOD_VERSION}

def _active(node: dict) -> bool:
    return node["status"] in {"ACTIVE", "WATCH", "REVIEW_REQUIRED"}

def evaluate_nodes(features: dict) -> dict[str, dict]:
    nodes: dict[str, dict] = {}
    dynamic = features.get("dynamic") or {}
    rain = next((dynamic.get(k) for k in ("rain_3h_mm","rain_1h_mm","rain_6h_mm","rain_24h_mm") if dynamic.get(k) is not None), None)
    rain_key = next((k for k in ("rain_3h_mm","rain_1h_mm","rain_6h_mm","rain_24h_mm") if dynamic.get(k) is not None), None)
    rain_index = dynamic.get("rain_1h_empirical_index")
    if rain is None:
        nodes["HEAVY_RAIN"] = _node("HEAVY_RAIN","INSUFFICIENT","UNKNOWN",missing=["현재 강우 관측값"])
    elif rain_index is None:
        nodes["HEAVY_RAIN"] = _node("HEAVY_RAIN","INSUFFICIENT","UNKNOWN",[_e("서울시 강우량",rain_key,rain,"mm")],["과거 강우분포 비교기준"])
    else:
        status = "ACTIVE" if float(rain_index) >= 90 else "WATCH" if float(rain_index) >= 75 else "INACTIVE"
        nodes["HEAVY_RAIN"] = _node("HEAVY_RAIN",status,"HIGH" if status=="ACTIVE" else "MEDIUM" if status=="WATCH" else "LOW",[_e("서울시 강우량",rain_key,rain,"mm"),_e("2021~2024 강우 통계","rain_1h_empirical_index",rain_index)])

    def relative_node(node_id: str, current_key: str, reference_keys: tuple[str,...], dataset: str):
        current = dynamic.get(current_key); reference = next((dynamic.get(k) for k in reference_keys if dynamic.get(k) is not None), None)
        if current is None: return _node(node_id,"INSUFFICIENT","UNKNOWN",missing=[current_key])
        if reference in (None,0): return _node(node_id,"INSUFFICIENT","UNKNOWN",[_e(dataset,current_key,current)],["비교 기준수위"])
        ratio=float(current)/float(reference); status="ACTIVE" if ratio>=1 else "WATCH" if ratio>=.8 else "INACTIVE"
        return _node(node_id,status,"HIGH" if status=="ACTIVE" else "MEDIUM" if status=="WATCH" else "LOW",[_e(dataset,current_key,current),_e(dataset,"reference_level",reference),_e(dataset,"relative_ratio",round(ratio,3))])
    nodes["SEWER_STRESS"] = relative_node("SEWER_STRESS","sewer_level_current",("sewer_level_p95","sewer_p95"),"서울시 하수관로 수위")
    nodes["RIVER_STRESS"] = relative_node("RIVER_STRESS","river_level_current",("river_planned_flood_level","river_control_level","river_inundation_level"),"서울시 하천 수위")

    terrain=features.get("terrain") or {}; coverage=terrain.get("dem_coverage_ratio_300m"); lowland=terrain.get("lowland_index_300m")
    if coverage is None or float(coverage)<.8 or lowland is None:
        nodes["LOWLAND_EXPOSURE"]=_node("LOWLAND_EXPOSURE","INSUFFICIENT","UNKNOWN",missing=["유효 DEM 300m 피복 및 저지대 지수"])
    else:
        status="ACTIVE" if float(lowland)>=20 else "WATCH" if float(lowland)>=10 else "INACTIVE"
        nodes["LOWLAND_EXPOSURE"]=_node("LOWLAND_EXPOSURE",status,"HIGH" if status=="ACTIVE" else "MEDIUM" if status=="WATCH" else "LOW",[_e("국토지리정보원 DEM","lowland_index_300m",lowland),_e("국토지리정보원 DEM","dem_coverage_ratio_300m",coverage)])

    flood=features.get("flood") or {}; historical=features.get("historical") or {}
    count=flood.get("historical_flood_count_300m"); ratio=flood.get("historical_flood_area_ratio_300m")
    if count is None: count=len(historical.get("hit_years_300m") or []) if historical else None
    if count is None: nodes["HISTORICAL_FLOOD_EXPOSURE"]=_node("HISTORICAL_FLOOD_EXPOSURE","INSUFFICIENT","UNKNOWN",missing=["침수흔적 공간결합"])
    else:
        status="ACTIVE" if int(count)>0 or bool(flood.get("historical_flood_overlap")) else "INACTIVE"
        nodes["HISTORICAL_FLOOD_EXPOSURE"]=_node("HISTORICAL_FLOOD_EXPOSURE",status,"HIGH" if status=="ACTIVE" else "LOW",[_e("서울시 침수흔적도","historical_flood_count_300m",count),_e("서울시 침수흔적도","historical_flood_area_ratio_300m",ratio or 0)])
    expected=flood.get("expected_flood_overlap")
    nodes["EXPECTED_FLOOD_EXPOSURE"]=_node("EXPECTED_FLOOD_EXPOSURE","INSUFFICIENT","UNKNOWN",missing=["풍수해 침수예상도 Geometry 공간결합"]) if expected is None else _node("EXPECTED_FLOOD_EXPOSURE","ACTIVE" if expected else "INACTIVE","HIGH" if expected else "LOW",[_e("서울시 풍수해 침수예상도","expected_flood_overlap",expected),_e("서울시 풍수해 침수예상도","expected_flood_area_ratio_300m",flood.get("expected_flood_area_ratio_300m"))])
    distance=flood.get("distance_to_nearest_pump_station_m")
    if distance is None: distance=(features.get("pump") or {}).get("nearest_pump_distance_m")
    if distance is None: nodes["DRAINAGE_LIMITATION"]=_node("DRAINAGE_LIMITATION","INSUFFICIENT","UNKNOWN",missing=["최근접 배수펌프장 거리"])
    else:
        status="ACTIVE" if float(distance)>3000 else "WATCH" if float(distance)>1500 else "INACTIVE"
        nodes["DRAINAGE_LIMITATION"]=_node("DRAINAGE_LIMITATION",status,"MEDIUM" if status!="INACTIVE" else "LOW",[_e("서울시 빗물펌프장 공간정보","distance_to_nearest_pump_station_m",distance,"m")])

    sources=[nodes[x] for x in ("HEAVY_RAIN","SEWER_STRESS","RIVER_STRESS","LOWLAND_EXPOSURE","DRAINAGE_LIMITATION")]
    independent=sum(x["status"] in {"ACTIVE","WATCH"} for x in sources)
    compound=independent>=2 and nodes["HEAVY_RAIN"]["status"] in {"ACTIVE","WATCH"}
    nodes["COMPOUND_HYDROLOGIC_STRESS"]=_node("COMPOUND_HYDROLOGIC_STRESS","ACTIVE" if compound else "INACTIVE","HIGH" if compound else "LOW",[ev for x in sources if x["status"] in {"ACTIVE","WATCH"} for ev in x["evidence"]])
    exposure_support=any(nodes[x]["status"] in {"ACTIVE","WATCH"} for x in ("LOWLAND_EXPOSURE","HISTORICAL_FLOOD_EXPOSURE","EXPECTED_FLOOD_EXPOSURE"))
    exposure=compound and exposure_support
    nodes["FLOOD_EXPOSURE"]=_node("FLOOD_EXPOSURE","ACTIVE" if exposure else "INACTIVE","HIGH" if exposure else "LOW",nodes["COMPOUND_HYDROLOGIC_STRESS"]["evidence"]+[ev for x in ("LOWLAND_EXPOSURE","HISTORICAL_FLOOD_EXPOSURE","EXPECTED_FLOOD_EXPOSURE") if nodes[x]["status"] in {"ACTIVE","WATCH"} for ev in nodes[x]["evidence"]])
    link=features.get("facility") or {}; elevators=int(link.get("elevator_count") or 0)
    nodes["ELEVATOR_SERVICE_IMPACT"]=_node("ELEVATOR_SERVICE_IMPACT","REVIEW_REQUIRED" if exposure and elevators>0 else "INACTIVE","MEDIUM" if exposure and elevators>0 else "LOW",[_e("승강기 설치 현황","elevator_count",elevators)] if elevators else [],["승강기 관련 설비의 실제 위치·방수상태"] if exposure and elevators>0 else [])
    for nid,missing in (("UNDERGROUND_EQUIPMENT_REVIEW","건물 내부 전기·기계설비 위치 및 방수상태"),("ACCESS_FUNCTION_REVIEW","지하 접근·주차 기능 배치 및 차수상태")):
        nodes[nid]=_node(nid,"REVIEW_REQUIRED" if exposure else "INACTIVE","MEDIUM" if exposure else "LOW",nodes["FLOOD_EXPOSURE"]["evidence"] if exposure else [],[missing] if exposure else [])
    facility_score=features.get("facility_vulnerability")
    functional=exposure and (elevators>0 or (facility_score is not None and float(facility_score)>=70))
    nodes["FUNCTIONAL_DISRUPTION"]=_node("FUNCTIONAL_DISRUPTION","REVIEW_REQUIRED" if functional else "INACTIVE","HIGH" if functional else "LOW",nodes["FLOOD_EXPOSURE"]["evidence"], ["실제 시설 고장·운영중단 관측"] if functional else [])
    nodes["RESILIENCE_DEGRADATION"]=_node("RESILIENCE_DEGRADATION","WATCH" if functional else "INACTIVE","MEDIUM" if functional else "LOW",nodes["FUNCTIONAL_DISRUPTION"]["evidence"])
    return nodes

def evaluate_paths(nodes: dict[str,dict]) -> list[dict]:
    definitions=[
      ("복합 수문 스트레스",["HEAVY_RAIN","COMPOUND_HYDROLOGIC_STRESS"]),
      ("침수 노출 경로",["HEAVY_RAIN","COMPOUND_HYDROLOGIC_STRESS","FLOOD_EXPOSURE"]),
      ("승강기 영향 점검",["HEAVY_RAIN","COMPOUND_HYDROLOGIC_STRESS","FLOOD_EXPOSURE","ELEVATOR_SERVICE_IMPACT"]),
      ("지하설비 확인",["HEAVY_RAIN","COMPOUND_HYDROLOGIC_STRESS","FLOOD_EXPOSURE","UNDERGROUND_EQUIPMENT_REVIEW"]),
      ("회복력 저하 점검",["HEAVY_RAIN","COMPOUND_HYDROLOGIC_STRESS","FLOOD_EXPOSURE","FUNCTIONAL_DISRUPTION","RESILIENCE_DEGRADATION"]),
    ]
    paths=[]
    for name,ids in definitions:
        if all(_active(nodes[x]) for x in ids):
            paths.append({"path_name":name,"nodes":ids,"status":"ACTIVE","severity":"HIGH" if len(ids)>=4 else "MEDIUM","evidence":[e for x in ids for e in nodes[x]["evidence"]],"missing_evidence":[m for x in ids for m in nodes[x]["missing_evidence"]]})
    return paths

def build_risk_graph(features: dict) -> dict:
    nodes=evaluate_nodes(features); paths=evaluate_paths(nodes)
    terminal_levels={"COMPOUND_HYDROLOGIC_STRESS":2,"FLOOD_EXPOSURE":3,
                     "ELEVATOR_SERVICE_IMPACT":4,"UNDERGROUND_EQUIPMENT_REVIEW":4,
                     "RESILIENCE_DEGRADATION":5}
    if paths: level=max(terminal_levels.get(p["nodes"][-1],1) for p in paths)
    elif any(x["status"] in {"ACTIVE","WATCH"} for x in nodes.values()): level=1
    else: level=0
    labels=["연쇄영향 미탐지","단일 환경 스트레스","복합 수문 스트레스","침수 노출 경로","시설 기능영향 점검 경로","복수 기능영향 및 회복력 저하 경로"]
    available=sum(bool(x["evidence"]) for x in nodes.values()); insufficient=sum(x["status"]=="INSUFFICIENT" for x in nodes.values())
    confidence="HIGH" if available>=8 and insufficient<=1 else "MEDIUM" if available>=4 else "LOW" if available else "INSUFFICIENT"
    return {"cascade_level":level,"cascade_label":labels[level],"active_path_count":len(paths),"nodes":list(nodes.values()),"paths":paths,"data_confidence":confidence,"method_type":METHOD_TYPE,"method_version":METHOD_VERSION,
            "priorities":[p for p in ["침수 노출 경로 확인" if level>=3 else None,"배수시설 상태 확인" if nodes["DRAINAGE_LIMITATION"]["status"]!="INACTIVE" else None,"승강기 관련 설비 점검" if nodes["ELEVATOR_SERVICE_IMPACT"]["status"]=="REVIEW_REQUIRED" else None,"지하 전기·기계설비 위치 및 방수상태 확인" if nodes["UNDERGROUND_EQUIPMENT_REVIEW"]["status"]=="REVIEW_REQUIRED" else None] if p]}

def _model_dict(row) -> dict:
    return {} if row is None else {c.name:getattr(row,c.name) for c in row.__table__.columns}

def collect_features(db: Session, complex_id: str, modified_dynamic: dict | None = None) -> dict:
    assessments=latest_assessments(db,complex_id); dynamic=assessments.get("dynamic_climate_stress"); facility=assessments.get("facility_vulnerability")
    return {"dynamic":modified_dynamic if modified_dynamic is not None else (dynamic.feature_snapshot if dynamic else {}),
      "terrain":_model_dict(db.scalars(select(TerrainFeature).where(TerrainFeature.complex_id==complex_id)).first()),
      "flood":_model_dict(db.get(FloodSpatialFeature,complex_id)),
      "historical":_model_dict(db.scalars(select(HistoricalFloodFeature).where(HistoricalFloodFeature.complex_id==complex_id)).first()),
      "pump":_model_dict(db.scalars(select(RainPumpProximityFeature).where(RainPumpProximityFeature.complex_id==complex_id)).first()),
      "facility":_model_dict(db.get(ComplexDataLink,complex_id)),"facility_vulnerability":facility.score if facility else None}

def _persist(db:Session,complex_id:str,mode:str,result:dict,inputs:dict,scenario_run_id:str|None=None)->dict:
    run_id=uuid.uuid4().hex; now=datetime.now(UTC)
    json_inputs=json.loads(json.dumps(inputs,ensure_ascii=False,default=str))
    json_result=json.loads(json.dumps(result,ensure_ascii=False,default=str))
    db.add(CascadeAnalysisRun(run_id=run_id,complex_id=complex_id,analysis_mode=mode,scenario_run_id=scenario_run_id,cascade_level=result["cascade_level"],active_path_count=len(result["paths"]),data_confidence=result["data_confidence"],method_type=METHOD_TYPE,method_version=METHOD_VERSION,input_snapshot=json_inputs,result_snapshot=json_result,created_at=now))
    for i,path in enumerate(result["paths"]): db.add(CascadePath(path_id=f"{run_id}:{i}",run_id=run_id,created_at=now,**path))
    db.commit(); return {"run_id":run_id,"complex_id":complex_id,"analysis_mode":mode,**result}

def analyze_realtime_cascade(db:Session,complex_id:str,persist:bool=True)->dict:
    if not db.get(SeoulComplexProfile,complex_id): raise LookupError("서울 분석 대상 단지가 아닙니다")
    features=collect_features(db,complex_id); result=build_risk_graph(features)
    return _persist(db,complex_id,"realtime",result,features) if persist else {"complex_id":complex_id,"analysis_mode":"realtime",**result}

def analyze_scenario_cascade(db:Session,stress_run_id:str,persist:bool=True)->dict:
    run=db.get(StressTestRun,stress_run_id)
    if not run: raise LookupError("시나리오 실행 결과가 없습니다")
    base=build_risk_graph(collect_features(db,run.complex_id,run.base_features.get("dynamic",run.base_features)))
    scenario_features=collect_features(db,run.complex_id,run.modified_features.get("dynamic",run.modified_features)); result=build_risk_graph(scenario_features)
    base_nodes={x["node_id"]:x for x in base["nodes"]}; scenario_nodes={x["node_id"]:x for x in result["nodes"]}
    result["comparison"]={"base_cascade_level":base["cascade_level"],"scenario_cascade_level":result["cascade_level"],"newly_activated_nodes":[k for k,v in scenario_nodes.items() if _active(v) and not _active(base_nodes[k])],"resolved_nodes":[k for k,v in base_nodes.items() if _active(v) and not _active(scenario_nodes[k])],"newly_activated_paths":[p["path_name"] for p in result["paths"] if p["path_name"] not in {x["path_name"] for x in base["paths"]}]}
    return _persist(db,run.complex_id,"scenario",result,scenario_features,stress_run_id) if persist else {"complex_id":run.complex_id,"analysis_mode":"scenario",**result}

def analyze_all_complexes(db:Session)->dict:
    ids=db.scalars(select(SeoulComplexProfile.complex_id).where(SeoulComplexProfile.analysis_eligible.is_(True))).all(); results=[analyze_realtime_cascade(db,x) for x in ids]
    return {"total":len(results),"levels":{str(i):sum(x["cascade_level"]==i for x in results) for i in range(6)},"results":results}
