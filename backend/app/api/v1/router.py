import json
import os
import uuid
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.v1.seoul import router as seoul_router
from backend.app.collectors.registry import load_registry
from backend.app.core.config import get_settings
from backend.app.db.base import (
    AIConversation,
    Alert,
    Complex,
    ComplexDataLink,
    DataCollectionRun,
    DataQualityResult,
    ModelVersion,
    Prediction,
    ReportArtifact,
    SeoulComplexProfile,
    SourceRecord,
    StressTestRun,
)
from backend.app.db.session import get_db
from backend.app.schemas.common import AlertOut, ComplexOut, PredictionOut
from backend.app.services.seoul_resilience_service import latest_assessments, profile_payload

router = APIRouter(prefix="/api/v1")
router.include_router(seoul_router)


@router.get("/frontend-config")
def frontend_config():
    """Expose browser-safe public configuration; never return server secrets."""
    auth_param = os.getenv("NAVER_MAP_AUTH_PARAM", "ncpKeyId").strip()
    if auth_param not in {"ncpKeyId", "ncpClientId"}:
        auth_param = "ncpKeyId"
    return {
        "naver_map_client_id": os.getenv("NAVER_MAP_CLIENT_ID", "").strip(),
        "naver_map_auth_param": auth_param,
        "environment": os.getenv("APP_ENV", "development"),
    }

@router.get("/complexes", response_model=list[ComplexOut])
def complexes(limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    return db.scalars(select(Complex).limit(limit)).all()

@router.get("/complexes/{complex_id}", response_model=ComplexOut)
def complex_detail(complex_id: str, db: Session = Depends(get_db)):
    item = db.get(Complex, complex_id)
    if not item: raise HTTPException(404, "단지 데이터 미수집")
    return item

@router.get("/complexes/{complex_id}/data-link")
def complex_data_link(complex_id: str, db: Session = Depends(get_db)):
    item = db.get(ComplexDataLink, complex_id)
    if not item: raise HTTPException(404, "연결된 설비·좌표 데이터 없음")
    return {column.name:getattr(item, column.name) for column in ComplexDataLink.__table__.columns}

def latest_risk(complex_id: str, risk_type: str, db: Session):
    item = db.scalar(select(Prediction).where(Prediction.complex_id == complex_id, Prediction.risk_type == risk_type).order_by(Prediction.prediction_time.desc()))
    if not item: raise HTTPException(404, "현재 예측 불가")
    return item

@router.get("/complexes/{complex_id}/flood-risk", response_model=PredictionOut)
def flood_risk(complex_id: str, db: Session = Depends(get_db)): return latest_risk(complex_id, "flood", db)

@router.get("/complexes/{complex_id}/facility-risk", response_model=PredictionOut)
def facility_risk(complex_id: str, db: Session = Depends(get_db)): return latest_risk(complex_id, "facility", db)

@router.get("/predictions/high-risk", response_model=list[PredictionOut])
def high_risk(min_probability: float = Query(.7, ge=0, le=1), db: Session = Depends(get_db)):
    return db.scalars(select(Prediction).where(Prediction.risk_probability >= min_probability).order_by(Prediction.risk_probability.desc()).limit(1000)).all()

@router.get("/predictions/distribution")
def prediction_distribution(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Prediction.risk_level, func.count(Prediction.prediction_id)).group_by(Prediction.risk_level)
    ).all()
    counts = {str(level): int(count) for level, count in rows}
    return {"total": sum(counts.values()), "items": [{"risk_level": level, "count": count} for level, count in counts.items()]}

def _prediction_detail(prediction_id: str, db: Session) -> dict:
    prediction = db.get(Prediction, prediction_id)
    if not prediction:
        raise HTTPException(404, "위험 선별 결과 없음")
    complex_item = db.get(Complex, prediction.complex_id)
    link = db.get(ComplexDataLink, prediction.complex_id)
    snapshot = prediction.feature_snapshot or {}
    components = snapshot.get("components") or {}
    if not components and prediction.risk_type == "facility":
        rate = float(snapshot.get("corrective_rate") or 0)
        components = {"base": .12, "corrective_history": .38 if snapshot.get("corrective_count", 0) else 0, "corrective_rate": .42 * rate}
    if not components and prediction.risk_type == "flood":
        elevation = snapshot.get("elevation_m")
        elevation_factor = min(max((35 - float(elevation)) / 35, 0), 1) if elevation is not None else 0
        components = {"base": .08, "rain": .40 * float(snapshot.get("rain_factor") or 0), "sewer_level": .32 * float(snapshot.get("sewer_factor") or 0), "low_elevation": .20 * elevation_factor}
    labels = {
        "base": "기본 점검값", "corrective_history": "시정권고 이력", "corrective_rate": "승강기 대비 시정권고 비율",
        "rain": "강우 관측", "sewer_level": "하수관로 수위", "low_elevation": "DEM 저지대",
    }
    breakdown = [{"factor": key, "label": labels.get(key, key), "contribution": round(float(value), 4), "points": round(float(value) * 100, 1)} for key, value in components.items()]
    if prediction.risk_type == "facility":
        evidence = [
            {"label": "연결 승강기", "value": snapshot.get("elevator_count", getattr(link, "elevator_count", 0)), "unit": "대", "source": "한국승강기안전공단 승강기 설치 현황"},
            {"label": "시정권고 누계", "value": snapshot.get("corrective_count", getattr(link, "corrective_count", 0)), "unit": "건", "source": "승강기 안전검사 시정권고 내역"},
            {"label": "선별 계산용 비율", "value": round(float(snapshot.get("corrective_rate") or 0) * 100, 1), "unit": "%", "source": "시정권고 건수÷연결 승강기 수, 최대 100% 적용"},
        ]
        formula = snapshot.get("formula") or "min(97점, 기본 12점 + 시정권고 이력 38점 + 시정권고 비율×42점)"
        limitation = "시정권고는 과거 누계 건수일 수 있으며 동일 승강기의 복수 이력이 포함될 수 있습니다. 고장 확률이 아니라 현장 점검 우선순위입니다."
    else:
        evidence = [
            {"label": "단지 표고", "value": snapshot.get("elevation_m"), "unit": "m", "source": "국토지리정보원 DEM"},
            {"label": "최근 강우량", "value": snapshot.get("rainfall_mm"), "unit": "mm", "source": "서울특별시 강우량 정보"},
            {"label": "강우 기준시각", "value": snapshot.get("rain_observed_at"), "unit": "", "source": "서울특별시 강우량 정보"},
            {"label": "하수관로 수위", "value": snapshot.get("sewer_level"), "unit": "", "source": "서울특별시 하수관로 수위 현황"},
            {"label": "수위 기준시각", "value": snapshot.get("sewer_observed_at"), "unit": "", "source": "서울특별시 하수관로 수위 현황"},
        ]
        formula = snapshot.get("formula") or "min(97점, 기본 8점 + 강우지수×40점 + 하수수위지수×32점 + 저지대지수×20점)"
        limitation = "관측소·하수 센서 값은 단지 내부의 직접 측정값이 아닐 수 있습니다. 침수 확률이 아니라 현장 점검 우선순위입니다."
    return {
        "prediction": {column.name: getattr(prediction, column.name) for column in Prediction.__table__.columns},
        "complex": None if not complex_item else {"complex_id": complex_item.complex_id, "complex_name": complex_item.complex_name, "address": complex_item.address, "latitude": complex_item.latitude, "longitude": complex_item.longitude},
        "data_link": None if not link else {column.name: getattr(link, column.name) for column in ComplexDataLink.__table__.columns},
        "score_breakdown": breakdown,
        "formula": formula,
        "evidence": evidence,
        "limitation": limitation,
        "decision": "우선 현장 점검" if prediction.risk_probability >= .85 else "점검 계획 반영",
    }

@router.get("/predictions/{prediction_id}/detail")
def prediction_detail(prediction_id: str, db: Session = Depends(get_db)):
    return _prediction_detail(prediction_id, db)

@router.post("/predictions/{prediction_id}/ai-explanation")
def prediction_ai_explanation(prediction_id: str, db: Session = Depends(get_db)):
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(503, "ANTHROPIC_API_KEY 미설정")
    detail = _prediction_detail(prediction_id, db)
    try:
        from anthropic import Anthropic
        message = Anthropic(api_key=settings.anthropic_api_key).messages.create(
            model=settings.claude_model,
            max_tokens=700,
            system=("당신은 LH-PREDICT 안전 관제 보조자다. 제공된 JSON만 근거로 사용한다. "
                    "이 수치는 ML 예측 확률이 아닌 규칙 기반 운영 선별지수임을 첫 문단에 명시한다. "
                    "점수가 높아진 핵심 요인, 실제 근거값, 현장 확인사항, 데이터 한계를 한국어로 구분해 간결하게 설명한다. "
                    "제공되지 않은 고장·침수 사실을 추정하거나 단정하지 않는다."),
            messages=[{"role": "user", "content": json.dumps(detail, ensure_ascii=False, default=str)}],
        )
        answer = "".join(block.text for block in message.content if getattr(block, "type", "") == "text")
    except Exception as exc:
        raise HTTPException(502, f"Claude 호출 실패: {type(exc).__name__}") from exc
    item = AIConversation(conversation_id=uuid.uuid4().hex, complex_id=detail["prediction"]["complex_id"], question=f"위험 선별 설명: {prediction_id}", answer=answer, created_at=datetime.now(UTC))
    db.add(item); db.commit()
    return {"prediction_id": prediction_id, "answer": answer, "conversation_id": item.conversation_id}

@router.get("/alerts", response_model=list[AlertOut])
def alerts(db: Session = Depends(get_db)): return db.scalars(select(Alert).order_by(Alert.created_at.desc())).all()

@router.patch("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge(alert_id: str, db: Session = Depends(get_db)):
    item = db.get(Alert, alert_id)
    if not item: raise HTTPException(404, "경보 없음")
    item.acknowledged = True; db.commit(); db.refresh(item); return item

@router.get("/data-quality")
def data_quality(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(Complex)) or 0
    latest = db.scalars(select(DataCollectionRun).order_by(DataCollectionRun.started_at.desc()).limit(50)).all()
    return {"status": "ok" if total else "unavailable", "complex_count": total, "message": "정상" if total else "데이터 미수집", "collection_runs": [{"collection_run_id":x.collection_run_id,"dataset_id":x.dataset_id,"status":x.status,"started_at":x.started_at,"record_count":x.record_count,"valid_count":x.valid_count,"quarantined_count":x.quarantined_count,"failure_reason":_safe_failure_reason(x.failure_reason)} for x in latest]}


def _safe_failure_reason(reason: str | None, limit: int = 500) -> str | None:
    """Keep diagnostics useful without returning SQL parameter dumps or huge payloads."""
    if not reason:
        return None
    first_line = reason.splitlines()[0].strip()
    return first_line if len(first_line) <= limit else f"{first_line[:limit - 1]}…"

@router.get("/data-sources")
def data_sources():
    return [{"dataset_id":x.id,"name":x.name,"mode":x.mode,"formats":x.formats,"domain":x.domain,"required":x.required,"api_url_env":x.api_url_env,"api_key_env":x.api_key_env} for x in load_registry().values()]

@router.get("/data-quality/{collection_run_id}")
def collection_quality(collection_run_id: str, db: Session = Depends(get_db)):
    run = db.get(DataCollectionRun, collection_run_id)
    if not run: raise HTTPException(404, "수집 실행 이력 없음")
    checks = db.scalars(select(DataQualityResult).where(DataQualityResult.collection_run_id == collection_run_id)).all()
    return {"run":{"collection_run_id":run.collection_run_id,"dataset_id":run.dataset_id,"status":run.status,"record_count":run.record_count,"valid_count":run.valid_count,"quarantined_count":run.quarantined_count,"failure_reason":_safe_failure_reason(run.failure_reason)},"checks":[{"check_name":x.check_name,"status":x.status,"failed_count":x.failed_count,"details":x.details} for x in checks]}

@router.get("/data-sources/{dataset_id}/records")
def source_records(dataset_id: str, limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    if dataset_id not in load_registry(): raise HTTPException(404, "등록되지 않은 데이터셋")
    rows = db.scalars(select(SourceRecord).where(SourceRecord.dataset_id == dataset_id).order_by(SourceRecord.collected_at.desc()).limit(limit)).all()
    return [{"source_record_id":x.source_record_id,"collection_run_id":x.collection_run_id,"data_version":x.data_version,"collected_at":x.collected_at,"payload":x.payload} for x in rows]

@router.get("/complex-links")
def complex_links(limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    rows = db.scalars(select(ComplexDataLink).order_by(ComplexDataLink.corrective_count.desc()).limit(limit)).all()
    return [{column.name:getattr(row,column.name) for column in ComplexDataLink.__table__.columns} for row in rows]

@router.get("/models")
def models(db: Session = Depends(get_db)):
    registered = db.scalars(select(ModelVersion).order_by(ModelVersion.created_at.desc())).all()
    items = [{column.name:getattr(item,column.name) for column in ModelVersion.__table__.columns} for item in registered]
    items.append({"model_id":"baseline-screening-v1","model_name":"기존 운영 선별 Baseline","model_type":"rule_baseline","version":"operational-screening-v1","status":"ACTIVE_BASELINE","status_reason":"ML 확률이 아닌 기존 운영 점검 선별지수"})
    return {"items":items,"message":"ML과 composite index를 별도 상태로 관리합니다."}

class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    complex_id: str | None = None
    scenario_id: str | None = None

@router.post("/ai/chat")
def ai_chat(payload: ChatRequest, db: Session = Depends(get_db)):
    settings = get_settings()
    if not settings.anthropic_api_key: raise HTTPException(503, "ANTHROPIC_API_KEY 미설정")
    context = {"complex_count":db.scalar(select(func.count()).select_from(Complex)) or 0,"prediction_count":db.scalar(select(func.count()).select_from(Prediction)) or 0,"alert_count":db.scalar(select(func.count()).select_from(Alert).where(Alert.acknowledged.is_(False))) or 0}
    if payload.complex_id:
        profile=db.get(SeoulComplexProfile,payload.complex_id)
        if profile:
            context["seoul_resilience"] = profile_payload(profile, latest_assessments(db, payload.complex_id))
        else:
            complex_item=db.get(Complex,payload.complex_id); link=db.get(ComplexDataLink,payload.complex_id)
            if complex_item: context["complex"]={"id":complex_item.complex_id,"name":complex_item.complex_name,"address":complex_item.address}
            if link: context["data_link"]={c.name:getattr(link,c.name) for c in ComplexDataLink.__table__.columns}
    if payload.scenario_id:
        scenario_rows = db.scalars(select(StressTestRun).where(StressTestRun.run_id.like(f"{payload.scenario_id}:%"))).all()
        context["scenario"] = {
            "notice": "USER_SCENARIO Stress Test 결과이며 실제 미래 예측 또는 재난 발생확률이 아님",
            "scenario_id": payload.scenario_id,
            "results": [{"complex_id": x.complex_id, "scenario_name": x.scenario_type,
                         "base_score": x.base_score, "scenario_score": x.scenario_score,
                         "scenario_input": x.modified_features.get("scenario_input"),
                         "source": x.modified_features.get("source"),
                         "top_changed_factors": x.modified_features.get("top_changed_factors", [])}
                        for x in scenario_rows[:125]],
        }
    try:
        from anthropic import Anthropic
        message=Anthropic(api_key=settings.anthropic_api_key).messages.create(model=settings.claude_model,max_tokens=900,system="당신은 LH-PREDICT RESILIENCE — SEOUL 안전 관제 보조자다. 제공된 구조화 JSON 사실만 사용한다. 점수나 확률을 직접 계산하거나 누락값을 추정하지 않는다. 회복력은 composite index, 시설 취약도는 고장확률이 아님을 명시하고 데이터 기준시각·품질·한계를 함께 설명한다.",messages=[{"role":"user","content":f"데이터 컨텍스트: {json.dumps(context, ensure_ascii=False, default=str)}\n\n질문: {payload.question}"}])
        answer="".join(block.text for block in message.content if getattr(block,"type","")=="text")
    except Exception as exc:
        raise HTTPException(502, f"Claude 호출 실패: {type(exc).__name__}") from exc
    item=AIConversation(conversation_id=uuid.uuid4().hex,complex_id=payload.complex_id,question=payload.question,answer=answer,created_at=datetime.now(UTC));db.add(item);db.commit()
    return {"conversation_id":item.conversation_id,"answer":answer,"created_at":item.created_at}

@router.get("/ai/conversations")
def conversations(db: Session = Depends(get_db)):
    rows=db.scalars(select(AIConversation).order_by(AIConversation.created_at.desc()).limit(100)).all();return [{"conversation_id":x.conversation_id,"complex_id":x.complex_id,"question":x.question,"answer":x.answer,"created_at":x.created_at} for x in rows]

@router.get("/ai/conversations/{conversation_id}")
def conversation(conversation_id: str, db: Session = Depends(get_db)):
    x=db.get(AIConversation,conversation_id)
    if not x: raise HTTPException(404,"대화 없음")
    return {"conversation_id":x.conversation_id,"complex_id":x.complex_id,"question":x.question,"answer":x.answer,"created_at":x.created_at}

@router.delete("/ai/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)):
    x=db.get(AIConversation,conversation_id)
    if x: db.delete(x);db.commit()
    return Response(status_code=204)

class ReportRequest(BaseModel):
    report_type: str
    complex_id: str | None = None

@router.post("/reports")
def create_report(payload: ReportRequest, db: Session = Depends(get_db)):
    now=datetime.now(UTC); report_id=uuid.uuid4().hex; title="LH 공동주택 AI 재난회복력 진단보고서"
    predictions=db.scalars(select(Prediction).order_by(Prediction.risk_probability.desc()).limit(100)).all(); alerts_count=db.scalar(select(func.count()).select_from(Alert).where(Alert.acknowledged.is_(False))) or 0
    complex_html=""
    if payload.complex_id:
        c=db.get(Complex,payload.complex_id); l=db.get(ComplexDataLink,payload.complex_id)
        if c: complex_html=f"<h2>{escape(c.complex_name)}</h2><p>{escape(c.address)}</p>"
        if l: complex_html+=f"<p>승강기 {l.elevator_count}대 · 시정권고 {l.corrective_count}건 · 좌표 연결 {'완료' if l.latitude is not None else '미완료'}</p>"
        profile=db.get(SeoulComplexProfile,payload.complex_id)
        if profile:
            assessments=latest_assessments(db,payload.complex_id)
            complex_html += "<h2>종합 회복력</h2>"
            for kind in ("resilience","climate_vulnerability","flood_susceptibility","dynamic_climate_stress","facility_vulnerability","data_confidence"):
                item=assessments.get(kind)
                value="데이터 부족" if not item or item.score is None else f"{item.score:.1f}점 ({escape(item.grade)})"
                complex_html += f"<p><b>{escape(kind)}</b>: {value} · {escape(item.method_version) if item else '미분석'} · {escape(item.data_quality_status) if item else 'INSUFFICIENT'}</p>"
    rows="".join(f"<tr><td>{escape(p.complex_id)}</td><td>{escape(p.risk_type)}</td><td>{p.risk_probability*100:.1f}%</td><td>{escape(p.risk_level)}</td></tr>" for p in predictions)
    html=f"<!doctype html><meta charset='utf-8'><title>{title}</title><style>body{{font-family:sans-serif;margin:40px;color:#132238}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:8px}}th{{background:#082b4c;color:white}}</style><h1>{title}</h1><p>생성시각 {now.isoformat()} · 미확인 경보 {alerts_count}건</p><p><b>분석 한계:</b> Resilience Score는 실제 재난 발생확률이 아니며 Facility Vulnerability는 실제 고장확률이 아닙니다. 침수흔적도 미적재로 Flood ML은 BLOCKED_BY_DATA 상태입니다.</p>{complex_html}<h2>기존 Baseline 참고</h2><table><tr><th>단지 ID</th><th>유형</th><th>운영 선별지수</th><th>등급</th></tr>{rows}</table>"
    output=get_settings().report_output_dir;output.mkdir(parents=True,exist_ok=True);path=output/f"{report_id}.html";path.write_text(html,encoding="utf-8")
    item=ReportArtifact(report_id=report_id,report_type=payload.report_type,complex_id=payload.complex_id,title=title,file_path=str(path),created_at=now);db.add(item);db.commit()
    return {"report_id":report_id,"title":title,"created_at":now,"download_url":f"/api/v1/reports/{report_id}/download"}

@router.get("/reports")
def reports(db: Session = Depends(get_db)):
    rows=db.scalars(select(ReportArtifact).order_by(ReportArtifact.created_at.desc()).limit(100)).all();return [{"report_id":x.report_id,"report_type":x.report_type,"complex_id":x.complex_id,"title":x.title,"created_at":x.created_at} for x in rows]

@router.get("/reports/{report_id}")
def report(report_id: str, db: Session = Depends(get_db)):
    x=db.get(ReportArtifact,report_id)
    if not x: raise HTTPException(404,"보고서 없음")
    return {"report_id":x.report_id,"report_type":x.report_type,"complex_id":x.complex_id,"title":x.title,"created_at":x.created_at}

@router.get("/reports/{report_id}/download")
def report_download(report_id: str, db: Session = Depends(get_db)):
    x=db.get(ReportArtifact,report_id)
    if not x or not Path(x.file_path).exists(): raise HTTPException(404,"보고서 파일 없음")
    return FileResponse(x.file_path,media_type="text/html",filename=f"LH-PREDICT-{report_id}.html")
