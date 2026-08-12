from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base, Complex, RiskAssessment, SeoulComplexProfile
from backend.app.services.seoul_resilience_service import (
    confidence_level,
    coordinate_in_seoul_extent,
    is_seoul_address,
    resilience_grade,
    run_stress_test,
)


def test_seoul_address_normalization_excludes_embedded_name():
    assert is_seoul_address("서울 강남구 자곡동 1")
    assert is_seoul_address("서울시 송파구 문정동 1")
    assert is_seoul_address("서울특별시 강서구 가양동 1")
    assert not is_seoul_address("경기도 파주시 독서울1길 1")


def test_coordinate_gate_and_score_ranges():
    assert coordinate_in_seoul_extent(37.55, 126.98) is True
    assert coordinate_in_seoul_extent(35.1, 129.0) is False
    assert coordinate_in_seoul_extent(None, None) is None
    assert resilience_grade(39) == "취약"
    assert resilience_grade(75) == "양호"
    assert confidence_level(34.9) == "INSUFFICIENT"


def test_stress_test_persists_actual_feature_changes():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as db:
        db.add(Complex(complex_id="S1", complex_name="서울 실제단지", address="서울특별시 강남구", latitude=37.5, longitude=127.0, source_name="fixture", source_url=None, collected_at=now, observed_at=now, data_version="test", validation_status="valid", collection_run_id="test"))
        db.add(SeoulComplexProfile(complex_id="S1", complex_name="서울 실제단지", address="서울특별시 강남구", normalized_address="서울특별시 강남구", latitude=37.5, longitude=127.0, district="강남구", household_count=10, building_count=1, completion_date=None, building_age_years=None, kapt_code=None, analysis_eligible=True, eligibility_reason="test", validation_status="VALIDATED", source_name="fixture", data_version="test", updated_at=now))
        for kind, score, features in (("flood_susceptibility", 40.0, {}), ("dynamic_climate_stress", 20.0, {"rain_1h_mm":10.0,"sewer_level_current":1.0}), ("climate_vulnerability", 31.0, {})):
            db.add(RiskAssessment(assessment_id=kind, complex_id="S1", assessment_type=kind, score=score, grade="보통", method_type="rule_baseline", method_version="test", feature_snapshot=features, explanation_snapshot={}, data_quality_status="COMPLETE", assessed_at=now, valid_from=now, valid_until=None, created_at=now))
        db.commit()
        result = run_stress_test(db, "S1", 50, 20)
        assert result.modified_features["rain_1h_mm"] == 15.0
        assert result.modified_features["sewer_level_current"] == 1.2
        assert result.scenario_score > result.base_score
