from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import (
    FloodSpatialFeature,
    ModelEvaluation,
    ModelVersion,
    RiskAssessment,
    SeoulComplexProfile,
)
from backend.app.db.session import get_db
from backend.app.schemas.seoul import (
    ScenarioRunRequest,
    ScenarioRunResponse,
    SeoulComplexSummary,
    StressTestOut,
    StressTestRequest,
)
from backend.app.services.flood_spatial_feature_service import (
    api_configuration_status,
    dataset_availability,
    feature_payload,
)
from backend.app.services.scenario_service import run_citywide_scenario
from backend.app.services.seoul_resilience_service import latest_assessments, profile_payload, run_stress_test

router = APIRouter(prefix="/seoul", tags=["Seoul Resilience"])
Db = Annotated[Session, Depends(get_db)]


def _summary(profile: SeoulComplexProfile, db: Session) -> SeoulComplexSummary:
    assessments = latest_assessments(db, profile.complex_id)
    resilience = assessments.get("resilience")
    confidence = assessments.get("data_confidence")
    return SeoulComplexSummary(
        complex_id=profile.complex_id, complex_name=profile.complex_name, address=profile.address,
        latitude=profile.latitude, longitude=profile.longitude, district=profile.district,
        analysis_eligible=profile.analysis_eligible, validation_status=profile.validation_status,
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
    return profile_payload(db.get(SeoulComplexProfile, complex_id), {assessment_type: item})["assessments"][assessment_type]


@router.get("/complexes/{complex_id}/resilience")
def resilience(complex_id: str, db: Db): return _assessment(complex_id, "resilience", db)


@router.get("/complexes/{complex_id}/climate")
def climate(complex_id: str, db: Db):
    rows = latest_assessments(db, complex_id)
    return {kind: profile_payload(db.get(SeoulComplexProfile, complex_id), {kind: rows[kind]})["assessments"][kind] for kind in ("flood_susceptibility", "dynamic_climate_stress", "climate_vulnerability") if kind in rows}


@router.get("/complexes/{complex_id}/facility")
def facility(complex_id: str, db: Db): return _assessment(complex_id, "facility_vulnerability", db)


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


@router.get("/hydrology-sources")
def hydrology_sources():
    return {
        "configuration": api_configuration_status(),
        "availability": dataset_availability(),
    }


@router.get("/high-risk", response_model=list[SeoulComplexSummary])
def high_risk(db: Db, max_resilience: float = Query(59, ge=0, le=100), limit: int = Query(100, ge=1, le=500)):
    profile_ids = db.scalars(select(RiskAssessment.complex_id).where(RiskAssessment.assessment_type == "resilience", RiskAssessment.score <= max_resilience).order_by(RiskAssessment.score).limit(limit)).all()
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
    return [{column.name:getattr(row,column.name) for column in ModelVersion.__table__.columns} for row in rows]


@router.get("/models/{model_id}/evaluation")
def model_evaluation(model_id: str, db: Db):
    model = db.get(ModelVersion, model_id)
    if not model:
        raise HTTPException(404, "모델 등록 정보가 없습니다")
    rows = db.scalars(select(ModelEvaluation).where(ModelEvaluation.model_id == model_id)).all()
    return {"model":{column.name:getattr(model,column.name) for column in ModelVersion.__table__.columns},"evaluations":[{column.name:getattr(row,column.name) for column in ModelEvaluation.__table__.columns} for row in rows]}
