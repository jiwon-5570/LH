"""Build Seoul profiles and transparent baseline assessments from real ingested data."""

from __future__ import annotations

import json
import math
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import rasterio
from pyproj import Transformer
from sqlalchemy import delete

from backend.app.db.base import (
    Base,
    ComplexDataLink,
    ModelVersion,
    RiskAssessment,
    SeoulComplexProfile,
)
from backend.app.db.session import SessionLocal, engine
from backend.app.services.seoul_resilience_service import (
    confidence_level,
    coordinate_in_seoul_extent,
    is_seoul_address,
    normalize_address,
    resilience_grade,
    risk_grade,
)

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime.now(UTC)


def latest_parquet(dataset_id: str) -> Path | None:
    paths = list((ROOT / "data" / "processed" / dataset_id).glob("*.parquet"))
    return max(paths, key=lambda path: path.stat().st_mtime) if paths else None


def compact(value: object) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").lower())


def safe_int(value: object) -> int | None:
    number = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(number) else int(number)


def date_and_age(value: object) -> tuple[str | None, float | None]:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None, None
    return parsed.strftime("%Y-%m-%d"), round((NOW.replace(tzinfo=None) - parsed).days / 365.2425, 1)


def dem_samples(rows: list[dict]) -> dict[str, float]:
    rasters = list((ROOT / "data" / "incoming" / "ngii_dem").glob("*.img"))
    datasets = [rasterio.open(path) for path in rasters]
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True)
    result: dict[str, float] = {}
    try:
        for row in rows:
            if row["latitude"] is None or row["longitude"] is None:
                continue
            x, y = transformer.transform(row["longitude"], row["latitude"])
            for dataset in datasets:
                if dataset.bounds.left <= x <= dataset.bounds.right and dataset.bounds.bottom <= y <= dataset.bounds.top:
                    value = float(next(dataset.sample([(x, y)]))[0])
                    if (dataset.nodata is None or value != dataset.nodata) and math.isfinite(value):
                        result[row["complex_id"]] = value
                    break
    finally:
        for dataset in datasets:
            dataset.close()
    return result


def observation_summary() -> tuple[dict[str, dict], dict[str, dict]]:
    rain: dict[str, dict] = {}
    sewer: dict[str, dict] = {}
    rain_path = latest_parquet("seoul_rainfall")
    if rain_path:
        frame = pd.read_parquet(rain_path)
        frame["time"] = pd.to_datetime(frame["observed_at"], errors="coerce", utc=True)
        frame["value"] = pd.to_numeric(frame["rainfall_mm"], errors="coerce")
        for district, group in frame.dropna(subset=["GU_NM", "time"]).groupby("GU_NM"):
            latest = group["time"].max()
            current = group[group["time"] == latest]
            rain[str(district)] = {"value": float(current["value"].max() or 0), "time": latest.to_pydatetime(), "station": str(current.iloc[0].get("station_name", ""))}
    sewer_path = latest_parquet("seoul_sewer_level")
    if sewer_path:
        frame = pd.read_parquet(sewer_path)
        frame["time"] = pd.to_datetime(frame["observed_at"], errors="coerce", utc=True)
        frame["value"] = pd.to_numeric(frame["water_level"], errors="coerce")
        for district, group in frame.dropna(subset=["SE_NM", "time"]).groupby("SE_NM"):
            latest = group["time"].max()
            current = group[group["time"] == latest]
            sewer[str(district)] = {"value": float(current["value"].max() or 0), "time": latest.to_pydatetime(), "sensor": str(current.iloc[0].get("sensor_id", "")), "p95": float(group["value"].quantile(.95) or 0)}
    return rain, sewer


def add_assessment(db, complex_id: str, kind: str, score: float | None, method: str, version: str, features: dict, factors: list[dict], quality: str) -> None:
    db.add(RiskAssessment(
        assessment_id=uuid.uuid4().hex, complex_id=complex_id, assessment_type=kind,
        score=None if score is None else round(max(0, min(100, score)), 2),
        grade=resilience_grade(score) if kind == "resilience" else (confidence_level(score or 0) if kind == "data_confidence" else risk_grade(score)),
        method_type=method, method_version=version, feature_snapshot=features,
        explanation_snapshot={"top_factors": factors[:5]}, data_quality_status=quality,
        assessed_at=NOW, valid_from=NOW, valid_until=None, created_at=NOW,
    ))


def main() -> None:
    Base.metadata.create_all(engine)
    lh_path = latest_parquet("lh_complexes")
    if not lh_path:
        raise FileNotFoundError("LH processed master가 없습니다")
    lh = pd.read_parquet(lh_path)
    lh = lh[lh["address"].map(is_seoul_address)].copy()
    kapt_list_path = latest_parquet("molit_complex_list")
    kapt_basic_path = latest_parquet("molit_complex_basic")
    kapt_list = pd.read_parquet(kapt_list_path) if kapt_list_path else pd.DataFrame()
    kapt_basic = pd.read_parquet(kapt_basic_path) if kapt_basic_path else pd.DataFrame()
    if not kapt_list.empty:
        kapt_list = kapt_list[kapt_list.get("as1", "").astype(str).eq("서울특별시")].copy()
        kapt_list["name_key"] = kapt_list["complex_name"].map(compact)
    basic_by_code = {} if kapt_basic.empty else kapt_basic.drop_duplicates("kapt_code").set_index("kapt_code").to_dict("index")
    links: dict[str, ComplexDataLink] = {}
    with SessionLocal() as db:
        links = {row.complex_id: row for row in db.query(ComplexDataLink).all()}

    profiles: list[dict] = []
    for row in lh.to_dict("records"):
        cid = str(row["complex_id"])
        link = links.get(cid)
        lat = link.latitude if link else None
        lon = link.longitude if link else None
        coordinate_ok = coordinate_in_seoul_extent(lat, lon)
        status = "VALIDATED" if coordinate_ok else ("ADDRESS_ONLY" if coordinate_ok is None else "REVIEW_REQUIRED")
        eligible = coordinate_ok is not False
        district_match = re.search(r"서울(?:특별시|시)\s+([^\s]+구)", str(row["address"]))
        district = district_match.group(1) if district_match else None
        match = pd.DataFrame()
        if not kapt_list.empty:
            match = kapt_list[kapt_list["name_key"] == compact(row["complex_name"])]
        kapt_code = str(match.iloc[0]["kapt_code"]) if len(match) == 1 else None
        basic = basic_by_code.get(kapt_code, {}) if kapt_code else {}
        completion, age = date_and_age(row.get("준공일") or basic.get("approval_date"))
        profiles.append({
            "complex_id": cid, "complex_name": str(row["complex_name"]), "address": str(row["address"]),
            "normalized_address": normalize_address(str(row["address"])), "latitude": lat, "longitude": lon,
            "district": district, "household_count": safe_int(row.get("세대수") or basic.get("households")),
            "building_count": safe_int(row.get("동수") or basic.get("building_count")),
            "completion_date": completion, "building_age_years": age, "kapt_code": kapt_code,
            "analysis_eligible": eligible, "eligibility_reason": "서울 주소 및 좌표 범위 검증" if coordinate_ok else ("서울 주소 확인; 좌표 미확보" if coordinate_ok is None else "서울 주소와 좌표 범위 불일치"),
            "validation_status": status, "source_name": str(row["source_name"]), "data_version": str(row["data_version"]), "updated_at": NOW,
        })

    elevations = dem_samples(profiles)
    rain_by_district, sewer_by_district = observation_summary()
    weights = json.loads((ROOT / "config" / "resilience_weights.json").read_text(encoding="utf-8"))["weights"]
    with SessionLocal() as db:
        db.execute(delete(RiskAssessment))
        db.execute(delete(SeoulComplexProfile))
        for values in profiles:
            db.add(SeoulComplexProfile(**values))
        db.flush()
        for values in profiles:
            cid = values["complex_id"]
            link = links.get(cid)
            elevation = elevations.get(cid)
            terrain_score = None if elevation is None else max(0.0, min(100.0, (35 - elevation) / 35 * 100))
            terrain_quality = "COMPLETE" if elevation is not None else "INSUFFICIENT"
            add_assessment(db, cid, "flood_susceptibility", terrain_score, "rule_baseline", "static-flood-baseline-v1", {"elevation_m": elevation, "flood_trace_status": "BLOCKED_BY_DATA", "expected_flood_geometry_status": "INSUFFICIENT"}, [{"factor":"elevation_m","label":"DEM 표고 기반 저지대 지수","value":elevation,"contribution_points":terrain_score}], terrain_quality)

            district = values["district"]
            rain = rain_by_district.get(district or "")
            sewer = sewer_by_district.get((district or "").removesuffix("구")) or sewer_by_district.get(district or "")
            rain_age = (NOW - rain["time"]).total_seconds() / 60 if rain else None
            sewer_age = (NOW - sewer["time"]).total_seconds() / 60 if sewer else None
            rain_factor = min(100.0, (rain["value"] / 30 * 100)) if rain else None
            sewer_factor = min(100.0, (sewer["value"] / sewer["p95"] * 100)) if sewer and sewer["p95"] > 0 else None
            parts = [x for x in (rain_factor, sewer_factor) if x is not None]
            dynamic_score = sum(parts) / len(parts) if parts else None
            dynamic_quality = "STALE" if parts and ((rain_age or 10**9) > 180 or (sewer_age or 10**9) > 180) else ("PARTIAL" if len(parts) < 2 else "COMPLETE")
            dynamic_features = {"rain_1h_mm": rain["value"] if rain else None, "rain_3h_mm": None, "rain_6h_mm": None, "rain_24h_mm": None, "rain_station_id": rain["station"] if rain else None, "rain_data_age_minutes": rain_age, "sewer_level_current": sewer["value"] if sewer else None, "nearest_sewer_sensor_id": sewer["sensor"] if sewer else None, "sewer_data_age_minutes": sewer_age, "distance_status": "BLOCKED_BY_DATA"}
            add_assessment(db, cid, "dynamic_climate_stress", dynamic_score, "rule_baseline", "dynamic-climate-stress-v1", dynamic_features, [{"factor":"rain","label":"최근 강우 관측","value":rain["value"] if rain else None,"contribution_points":rain_factor},{"factor":"sewer","label":"하수관로 수위","value":sewer["value"] if sewer else None,"contribution_points":sewer_factor}], dynamic_quality)

            climate_score = None if terrain_score is None and dynamic_score is None else 0.55 * (terrain_score or 0) + 0.45 * (dynamic_score or 0)
            climate_quality = "INSUFFICIENT" if climate_score is None else ("STALE" if dynamic_quality == "STALE" else "PARTIAL")
            add_assessment(db, cid, "climate_vulnerability", climate_score, "composite_index", "climate-vulnerability-v1", {"static_flood_susceptibility":terrain_score,"dynamic_climate_stress":dynamic_score}, [{"factor":"static","label":"정적 침수 취약도","value":terrain_score,"contribution_points":None if terrain_score is None else terrain_score*.55},{"factor":"dynamic","label":"동적 기후 스트레스","value":dynamic_score,"contribution_points":None if dynamic_score is None else dynamic_score*.45}], climate_quality)

            elevator_count = int(link.elevator_count if link else 0)
            corrective_count = int(link.corrective_count if link else 0)
            if elevator_count:
                corrective_rate = min(corrective_count / elevator_count, 1)
                facility_score = min(100.0, 12 + (38 if corrective_count else 0) + 42 * corrective_rate)
                facility_quality = "PARTIAL"
            else:
                corrective_rate = None; facility_score = None; facility_quality = "INSUFFICIENT"
            add_assessment(db, cid, "facility_vulnerability", facility_score, "rule_baseline", "facility-vulnerability-baseline-v1", {"elevator_count":elevator_count,"corrective_action_count":corrective_count,"corrective_rate":corrective_rate,"model_status":"NOT_READY"}, [{"factor":"corrective","label":"승강기 시정권고 이력","value":corrective_count,"contribution_points":facility_score}], facility_quality)

            components = {"dem_coverage":100 if elevation is not None else 0,"rain_freshness":100 if rain_age is not None and rain_age <= 180 else 20 if rain else 0,"sewer_freshness":100 if sewer_age is not None and sewer_age <= 180 else 20 if sewer else 0,"flood_history_availability":0,"facility_linkage":100 if elevator_count else 0,"kapt_linkage":100 if values["kapt_code"] else 0,"coordinate_validation":100 if values["validation_status"] == "VALIDATED" else 40 if values["validation_status"] == "ADDRESS_ONLY" else 0}
            confidence = sum(components.values()) / len(components)
            add_assessment(db, cid, "data_confidence", confidence, "composite_index", "data-confidence-v1", components, sorted(({"factor":k,"label":k,"value":v,"contribution_points":v/len(components)} for k,v in components.items()), key=lambda x:x["value"]), confidence_level(confidence))

            if climate_score is None and facility_score is None:
                resilience = None
            else:
                unknown_exposure = 50.0
                vulnerability = (weights["climate_vulnerability"]*(climate_score or 50) + weights["terrain_drainage_vulnerability"]*(terrain_score or 50) + weights["facility_vulnerability"]*(facility_score or 50) + weights["historical_exposure"]*unknown_exposure + weights["data_uncertainty"]*(100-confidence))
                resilience = 100 - vulnerability
            top = sorted([
                {"factor":"climate_vulnerability","label":"기후재난 취약성","value":climate_score,"contribution_points":None if climate_score is None else weights["climate_vulnerability"]*climate_score},
                {"factor":"terrain","label":"지형·배수 취약성","value":terrain_score,"contribution_points":None if terrain_score is None else weights["terrain_drainage_vulnerability"]*terrain_score},
                {"factor":"facility","label":"시설 취약성","value":facility_score,"contribution_points":None if facility_score is None else weights["facility_vulnerability"]*facility_score},
                {"factor":"data_uncertainty","label":"데이터 불확실성","value":100-confidence,"contribution_points":weights["data_uncertainty"]*(100-confidence)},
            ], key=lambda x: x["contribution_points"] or -1, reverse=True)
            add_assessment(db, cid, "resilience", resilience, "composite_index", "resilience-composite-v1", {"climate_vulnerability":climate_score,"terrain_drainage_vulnerability":terrain_score,"facility_vulnerability":facility_score,"historical_exposure":None,"data_confidence":confidence,"weights":weights,"not_a_probability":True}, top, confidence_level(confidence))

        for model_id, name, target, reason in (
            ("flood-grid-v1", "서울 Grid Flood Susceptibility", "historical_flood_overlap", "행정안전부 침수흔적도 미적재"),
            ("facility-next-inspection-v1", "승강기 차기검사 비통과 위험", "next_inspection_non_pass", "시간순 승강기 연결 학습표 및 외부검증 미완료"),
        ):
            db.merge(ModelVersion(model_id=model_id, model_name=name, model_type="classifier", version="v1", target_name=target, training_started_at=None, training_finished_at=None, training_data_version=None, feature_list=[], artifact_path=None, status="BLOCKED_BY_DATA" if model_id.startswith("flood") else "NOT_READY", status_reason=reason, created_at=NOW))
        db.commit()
    print({"seoul_profiles":len(profiles),"analysis_eligible":sum(x["analysis_eligible"] for x in profiles),"coordinate_validated":sum(x["validation_status"]=="VALIDATED" for x in profiles),"dem_coverage":len(elevations),"flood_ml":"BLOCKED_BY_DATA","facility_ml":"NOT_READY"})


if __name__ == "__main__":
    main()
