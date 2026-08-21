from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.db.base import Base, Complex, RiskAssessment, SeoulComplexProfile, StressTestRun
from backend.app.schemas.seoul import ScenarioRunRequest
from backend.app.services.scenario_service import run_citywide_scenario


def _database() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    now = datetime.now(UTC)
    db.add(Complex(complex_id="S1",complex_name="테스트단지",address="서울특별시 강남구",latitude=37.5,longitude=127.0,source_name="fixture",source_url=None,collected_at=now,observed_at=now,data_version="test",validation_status="valid",collection_run_id="test"))
    db.add(SeoulComplexProfile(complex_id="S1",complex_name="테스트단지",address="서울특별시 강남구",normalized_address="서울특별시 강남구",latitude=37.5,longitude=127.0,district="강남구",household_count=10,building_count=1,completion_date=None,building_age_years=None,kapt_code=None,analysis_eligible=True,eligibility_reason="test",validation_status="VALIDATED",source_name="fixture",data_version="test",updated_at=now))
    fixtures = [
        ("dynamic_climate_stress",20.0,{"rain_1h_mm":10.0,"rain_1h_empirical_index":20.0,"sewer_level_current":1.0}),
        ("climate_vulnerability",31.0,{"static_flood_susceptibility":40.0,"dynamic_climate_stress":20.0}),
        ("resilience",70.0,{"climate_vulnerability":31.0,"terrain_drainage_vulnerability":40.0,"facility_vulnerability":30.0,"historical_exposure":20.0,"data_confidence":80.0}),
        ("data_confidence",80.0,{}),
    ]
    for i,(kind,score,features) in enumerate(fixtures):
        db.add(RiskAssessment(assessment_id=f"a{i}",complex_id="S1",assessment_type=kind,score=score,grade="보통",method_type="composite_index",method_version="test",feature_snapshot=features,explanation_snapshot={},data_quality_status="COMPLETE",assessed_at=now,valid_from=now,valid_until=None,created_at=now))
    db.commit()
    return db


def test_scenario_input_validation_ranges():
    with pytest.raises(ValidationError):
        ScenarioRunRequest(rain_change_pct=201)
    with pytest.raises(ValidationError):
        ScenarioRunRequest(sewer_change_pct=float("inf"))


def test_citywide_scenario_recalculates_and_persists_without_overwriting_realtime():
    db = _database()
    before = db.scalar(select(func.count()).select_from(RiskAssessment))
    payload = ScenarioRunRequest(rain_change_pct=50,sewer_change_pct=20,river_change_pct=10)
    response = run_citywide_scenario(db,payload)
    result = response["complex_results"][0]
    assert response["scenario_input"] is True
    assert response["source"] == "USER_SCENARIO"
    assert result["scenario_features"]["rain_1h_mm"] == 15.0
    assert result["scenario_features"]["sewer_level_current"] == 1.2
    assert result["base_features"]["rain_1h_mm"] == 10.0
    assert result["resilience_delta"] == pytest.approx(result["scenario_resilience_score"]-70.0,abs=.01)
    assert db.scalar(select(func.count()).select_from(RiskAssessment)) == before
    stored = db.scalar(select(StressTestRun))
    assert stored is not None
    assert stored.method_version == "scenario-baseline-v1"
    assert stored.modified_features["source"] == "USER_SCENARIO"
    db.close()
