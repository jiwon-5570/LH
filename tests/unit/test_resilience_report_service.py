from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base, Complex, RiskAssessment, SeoulComplexProfile
from backend.app.services.resilience_report_service import build_report_payload, generate_report


def _database() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    now = datetime.now(UTC)
    rows = [
        ("A", "가단지", "강남구", 40.0),
        ("B", "나단지", "강남구", 80.0),
        ("C", "다단지", "강북구", None),
    ]
    for index, (complex_id, name, district, score) in enumerate(rows):
        db.add(
            Complex(
                complex_id=complex_id,
                complex_name=name,
                address=f"서울특별시 {district}",
                latitude=37.5 + index / 100,
                longitude=127.0 + index / 100,
                source_name="fixture",
                source_url=None,
                collected_at=now,
                observed_at=now,
                data_version="test",
                validation_status="valid",
                collection_run_id="test",
            )
        )
        db.add(
            SeoulComplexProfile(
                complex_id=complex_id,
                complex_name=name,
                address=f"서울특별시 {district}",
                normalized_address=f"서울특별시 {district}",
                latitude=37.5 + index / 100,
                longitude=127.0 + index / 100,
                district=district,
                household_count=100,
                building_count=2,
                completion_date=None,
                building_age_years=None,
                kapt_code=None,
                analysis_eligible=True,
                eligibility_reason="test",
                validation_status="VALIDATED",
                source_name="fixture",
                data_version="test",
                updated_at=now,
            )
        )
        if score is not None:
            db.add(
                RiskAssessment(
                    assessment_id=f"risk-{complex_id}",
                    complex_id=complex_id,
                    assessment_type="resilience",
                    score=score,
                    grade="보통",
                    method_type="composite_index",
                    method_version="test",
                    feature_snapshot={},
                    explanation_snapshot={
                        "top_factors": [{"label": "검증 요인", "value": index + 1, "unit": "점", "source": "fixture"}]
                    },
                    data_quality_status="COMPLETE",
                    assessed_at=now,
                    valid_from=now,
                    valid_until=None,
                    created_at=now,
                )
            )
    db.commit()
    return db


def test_seoul_report_excludes_missing_scores_from_average():
    db = _database()
    report = build_report_payload(db, "resilience", "seoul", None)
    assert report["summary"] == {
        "total_complexes": 3,
        "analysis_available": 2,
        "average_resilience": 60.0,
        "vulnerable": 0,
        "caution": 1,
        "normal": 0,
        "good": 1,
        "insufficient": 1,
    }
    assert [row["complex_id"] for row in report["ranking"]] == ["A", "B"]
    assert "[종합 판단]" in report["ai_explanation"]
    assert "가단지" in report["ai_explanation"]
    assert report["recommendations"][0]["evidence"]
    db.close()


def test_complex_report_contains_real_comparison_and_factors():
    db = _database()
    report = build_report_payload(db, "resilience", "complex", "A")
    assert report["comparison"]["selected"] == 40.0
    assert report["comparison"]["district_average"] == 60.0
    assert report["comparison"]["seoul_average"] == 60.0
    assert report["top_factors"][0]["label"] == "검증 요인"
    assert report["detail"]["profile"]["latitude"] == 37.5
    db.close()


def test_invalid_scope_does_not_create_fake_report():
    db = _database()
    with pytest.raises(LookupError):
        build_report_payload(db, "resilience", "complex", "missing")
    with pytest.raises(ValueError):
        build_report_payload(db, "unknown", "seoul", None)
    db.close()


def test_generate_report_persists_snapshot_and_two_files(tmp_path, monkeypatch):
    db = _database()
    settings = type("Settings", (), {"report_output_dir": tmp_path, "anthropic_api_key": "", "claude_model": ""})()
    monkeypatch.setattr("backend.app.services.resilience_report_service.get_settings", lambda: settings)
    report = generate_report(db, "resilience", "district", "강남구")
    assert (tmp_path / f"{report['report_id']}.html").is_file()
    assert any(path.suffix == ".pdf" and path.stat().st_size > 0 for path in tmp_path.iterdir())
    assert report["html_download_url"].endswith("/download/html")
    assert report["pdf_download_url"].endswith("/download/pdf")
    db.close()
