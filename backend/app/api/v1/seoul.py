from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import (
    FloodSpatialFeature,
    ModelEvaluation,
    ModelVersion,
    ReportArtifact,
    ResilienceReportSnapshot,
    RiskAssessment,
    SeoulComplexProfile,
)
from backend.app.db.session import get_db
from backend.app.schemas.seoul import (
    ResilienceReportRequest,
    ResilienceReportResponse,
    ScenarioRunRequest,
    ScenarioRunResponse,
    SeoulComplexSummary,
    StressTestOut,
    StressTestRequest,
)
from backend.app.services.cascading_risk_service import (
    analyze_all_complexes,
    analyze_realtime_cascade,
    analyze_scenario_cascade,
)
from backend.app.services.flood_spatial_feature_service import (
    api_configuration_status,
    dataset_availability,
    feature_payload,
)
from backend.app.services.resilience_report_service import REPORT_TYPES, generate_report
from backend.app.services.scenario_service import run_citywide_scenario
from backend.app.services.seoul_resilience_service import latest_assessments, profile_payload, run_stress_test

router = APIRouter(prefix="/seoul", tags=["Seoul Resilience"])
Db = Annotated[Session, Depends(get_db)]


@router.get("/reports/options")
def report_options(db: Db):
    profiles = db.scalars(
        select(SeoulComplexProfile).order_by(SeoulComplexProfile.district, SeoulComplexProfile.complex_name)
    ).all()
    return {
        "report_types": [{"value": key, "label": label} for key, label in REPORT_TYPES.items()],
        "districts": sorted({row.district for row in profiles if row.district}),
        "complexes": [
            {"complex_id": row.complex_id, "complex_name": row.complex_name, "district": row.district}
            for row in profiles
        ],
    }


@router.post("/reports/generate", response_model=ResilienceReportResponse)
def create_resilience_report(payload: ResilienceReportRequest, db: Db):
    if payload.scope_type != "seoul" and not payload.scope_value:
        raise HTTPException(422, "자치구 또는 단지를 선택하세요")
    try:
        return generate_report(db, payload.report_type, payload.scope_type, payload.scope_value, payload.reference_date)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/reports/{report_id}", response_model=ResilienceReportResponse)
def report_snapshot(report_id: str, db: Db):
    artifact = db.get(ReportArtifact, report_id)
    snapshot = db.get(ResilienceReportSnapshot, report_id)
    if not artifact or not snapshot:
        raise HTTPException(404, "보고서 스냅샷이 없습니다")
    return {
        "report_id": report_id,
        **snapshot.payload_snapshot,
        "html_download_url": f"/api/v1/seoul/reports/{report_id}/download/html",
        "pdf_download_url": f"/api/v1/seoul/reports/{report_id}/download/pdf",
    }


def _report_file(report_id: str, kind: str, db: Session) -> FileResponse:
    artifact = db.get(ReportArtifact, report_id)
    snapshot = db.get(ResilienceReportSnapshot, report_id)
    if not artifact or not snapshot:
        raise HTTPException(404, "보고서 스냅샷이 없습니다")
    path = Path(artifact.file_path if kind == "html" else snapshot.pdf_path or "")
    if not path.is_file():
        raise HTTPException(404, "생성된 보고서 파일이 없습니다")
    media = "text/html; charset=utf-8" if kind == "html" else "application/pdf"
    return FileResponse(path, media_type=media, filename=path.name)


@router.get("/reports/{report_id}/download/html")
def download_report_html(report_id: str, db: Db):
    return _report_file(report_id, "html", db)


@router.get("/reports/{report_id}/download/pdf")
def download_report_pdf(report_id: str, db: Db):
    return _report_file(report_id, "pdf", db)


def _summary(profile: SeoulComplexProfile, db: Session) -> SeoulComplexSummary:
    assessments = latest_assessments(db, profile.complex_id)
    resilience = assessments.get("resilience")
    confidence = assessments.get("data_confidence")
    return SeoulComplexSummary(
        complex_id=profile.complex_id,
        complex_name=profile.complex_name,
        address=profile.address,
        latitude=profile.latitude,
        longitude=profile.longitude,
        district=profile.district,
        analysis_eligible=profile.analysis_eligible,
        validation_status=profile.validation_status,
        resilience_score=resilience.score if resilience else None,
        resilience_grade=resilience.grade if resilience else None,
        data_confidence=confidence.score if confidence else None,
        assessed_at=resilience.assessed_at if resilience else None,
    )


@router.get("/complexes", response_model=list[SeoulComplexSummary])
def complexes(db: Db, district: str | None = None, eligible_only: bool = False, limit: int = Query(500, ge=1, le=1000)):
    query = select(SeoulComplexProfile).order_by(SeoulComplexProfile.complex_name).limit(limit)
    if district:
        query = query.where(SeoulComplexProfile.district == district)
    if eligible_only:
        query = query.where(SeoulComplexProfile.analysis_eligible.is_(True))
    return [_summary(item, db) for item in db.scalars(query).all()]


@router.get("/complexes/{complex_id}")
def complex_detail(complex_id: str, db: Db):
    item = db.get(SeoulComplexProfile, complex_id)
    if not item:
        raise HTTPException(404, "서울 분석 대상 단지가 아닙니다")
    return profile_payload(item, latest_assessments(db, complex_id))


def _assessment(complex_id: str, assessment_type: str, db: Session):
    item = latest_assessments(db, complex_id).get(assessment_type)
    if not item:
        raise HTTPException(404, "해당 분석 결과가 없습니다")
    return profile_payload(db.get(SeoulComplexProfile, complex_id), {assessment_type: item})["assessments"][
        assessment_type
    ]


@router.get("/complexes/{complex_id}/resilience")
def resilience(complex_id: str, db: Db):
    return _assessment(complex_id, "resilience", db)


@router.get("/complexes/{complex_id}/climate")
def climate(complex_id: str, db: Db):
    rows = latest_assessments(db, complex_id)
    return {
        kind: profile_payload(db.get(SeoulComplexProfile, complex_id), {kind: rows[kind]})["assessments"][kind]
        for kind in ("flood_susceptibility", "dynamic_climate_stress", "climate_vulnerability")
        if kind in rows
    }


@router.get("/complexes/{complex_id}/facility")
def facility(complex_id: str, db: Db):
    return _assessment(complex_id, "facility_vulnerability", db)


@router.get("/complexes/{complex_id}/explanations")
def explanations(complex_id: str, db: Db):
    rows = latest_assessments(db, complex_id)
    return {kind: row.explanation_snapshot for kind, row in rows.items()}


def _flood_feature(complex_id: str, section: str | None, db: Session):
    if not db.get(SeoulComplexProfile, complex_id):
        raise HTTPException(404, "서울 분석 대상 단지가 아닙니다")
    return feature_payload(db.get(FloodSpatialFeature, complex_id), section)


@router.get("/complexes/{complex_id}/flood-history")
def flood_history(complex_id: str, db: Db):
    return _flood_feature(complex_id, "flood-history", db)


@router.get("/complexes/{complex_id}/flood-forecast")
def flood_forecast(complex_id: str, db: Db):
    return _flood_feature(complex_id, "flood-forecast", db)


@router.get("/complexes/{complex_id}/rainfall")
def rainfall(complex_id: str, db: Db):
    return _flood_feature(complex_id, "rainfall", db)


@router.get("/complexes/{complex_id}/drainage")
def drainage(complex_id: str, db: Db):
    return _flood_feature(complex_id, "drainage", db)


@router.get("/complexes/{complex_id}/river")
def river(complex_id: str, db: Db):
    return _flood_feature(complex_id, "river", db)


@router.get("/complexes/{complex_id}/flood-features")
def flood_features(complex_id: str, db: Db):
    return _flood_feature(complex_id, None, db)


@router.get("/complexes/{complex_id}/hydrology")
def hydrology(complex_id: str, db: Db):
    """Compact, evidence-only hydrology view reused by UI, scenarios and reports."""
    profile = db.get(SeoulComplexProfile, complex_id)
    if not profile:
        raise HTTPException(404, "서울 분석 대상 단지가 아닙니다")
    item = db.get(FloodSpatialFeature, complex_id)
    if item is None:
        return {
            "complex_id": complex_id,
            "status": "NOT_READY",
            "reason": "flood_spatial_features has not been built",
        }
    metadata = item.source_metadata or {}
    return {
        "complex_id": complex_id,
        "analysis_eligibility": {
            "profile_available": True,
            "spatial_analysis_available": profile.latitude is not None and profile.longitude is not None,
            "hydrology_analysis_available": item.data_quality_status not in {"INSUFFICIENT", "FAILED"},
        },
        "historical_flood": feature_payload(item, "flood-history"),
        "expected_flood": feature_payload(item, "flood-forecast"),
        "rainfall": {
            **feature_payload(item, "rainfall"),
            "station": metadata.get("rain_station_match", {}),
        },
        "drainage": feature_payload(item, "drainage"),
        "river": {
            **feature_payload(item, "river"),
            "station": metadata.get("river_station_match", {}),
        },
        "dataset_statuses": item.dataset_statuses,
        "source_metadata": metadata,
        "data_quality_status": item.data_quality_status,
        "data_version": item.data_version,
        "processed_at": item.processed_at,
    }


@router.get("/complexes/{complex_id}/cascade")
def cascade(complex_id: str, db: Db):
    try:
        return analyze_realtime_cascade(db, complex_id, persist=False)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/complexes/{complex_id}/cascade/analyze")
def analyze_cascade(complex_id: str, db: Db):
    try:
        return analyze_realtime_cascade(db, complex_id, persist=True)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/stress-tests/{stress_run_id}/cascade")
def scenario_cascade(stress_run_id: str, db: Db):
    try:
        return analyze_scenario_cascade(db, stress_run_id, persist=False)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/cascade/analyze-all")
def cascade_all(db: Db):
    return analyze_all_complexes(db)


@router.get("/hydrology-sources")
def hydrology_sources():
    return {
        "configuration": api_configuration_status(),
        "availability": dataset_availability(),
    }


@router.get("/high-risk", response_model=list[SeoulComplexSummary])
def high_risk(db: Db, max_resilience: float = Query(59, ge=0, le=100), limit: int = Query(100, ge=1, le=500)):
    profile_ids = db.scalars(
        select(RiskAssessment.complex_id)
        .where(RiskAssessment.assessment_type == "resilience", RiskAssessment.score <= max_resilience)
        .order_by(RiskAssessment.score)
        .limit(limit)
    ).all()
    profiles = [db.get(SeoulComplexProfile, cid) for cid in profile_ids]
    return [_summary(item, db) for item in profiles if item]


@router.post("/stress-test", response_model=StressTestOut)
def stress_test(payload: StressTestRequest, db: Db):
    try:
        return run_stress_test(db, payload.complex_id, payload.rain_change_pct, payload.sewer_change_pct)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/scenarios/run", response_model=ScenarioRunResponse)
def scenario_run(payload: ScenarioRunRequest, db: Db):
    if not payload.apply_to_all_complexes and not payload.target_complex_id:
        raise HTTPException(422, "단일 단지 시나리오는 target_complex_id가 필요합니다")
    return run_citywide_scenario(db, payload)


@router.get("/models")
def models(db: Db):
    rows = db.scalars(select(ModelVersion).order_by(ModelVersion.created_at.desc())).all()
    return [{column.name: getattr(row, column.name) for column in ModelVersion.__table__.columns} for row in rows]


@router.get("/models/{model_id}/evaluation")
def model_evaluation(model_id: str, db: Db):
    model = db.get(ModelVersion, model_id)
    if not model:
        raise HTTPException(404, "모델 등록 정보가 없습니다")
    rows = db.scalars(select(ModelEvaluation).where(ModelEvaluation.model_id == model_id)).all()
    return {
        "model": {column.name: getattr(model, column.name) for column in ModelVersion.__table__.columns},
        "evaluations": [
            {column.name: getattr(row, column.name) for column in ModelEvaluation.__table__.columns} for row in rows
        ],
    }
