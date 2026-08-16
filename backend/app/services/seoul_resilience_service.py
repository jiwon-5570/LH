from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import RiskAssessment, SeoulComplexProfile, StressTestRun

ROOT = Path(__file__).resolve().parents[3]


def normalize_address(value: str) -> str:
    text = re.sub(r"\([^)]*\)", " ", str(value or "").strip())
    text = text.replace("서울시", "서울특별시")
    text = re.sub(r"^서울\s+", "서울특별시 ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_seoul_address(value: str) -> bool:
    return normalize_address(value).startswith("서울특별시")


def coordinate_in_seoul_extent(latitude: float | None, longitude: float | None) -> bool | None:
    """Coarse rejection gate only; it is not a substitute for an admin polygon."""
    if latitude is None or longitude is None:
        return None
    return 37.413 <= latitude <= 37.715 and 126.734 <= longitude <= 127.270


def risk_grade(score: float | None) -> str:
    if score is None:
        return "미분석"
    if score >= 85:
        return "매우 높음"
    if score >= 70:
        return "높음"
    if score >= 45:
        return "보통"
    return "낮음"


def resilience_grade(score: float | None) -> str:
    if score is None:
        return "데이터 부족"
    if score <= 39:
        return "취약"
    if score <= 59:
        return "주의"
    if score <= 74:
        return "보통"
    return "양호"


def confidence_level(score: float) -> str:
    if score >= 80:
        return "HIGH"
    if score >= 60:
        return "MEDIUM"
    if score >= 35:
        return "LOW"
    return "INSUFFICIENT"


def renormalized_vulnerability(values: dict[str, float | None], weights: dict[str, float]) -> tuple[float | None, dict[str, float], list[str]]:
    available = {key:value for key,value in values.items() if value is not None and key in weights}
    missing = [key for key in weights if key not in available]
    total = sum(weights[key] for key in available)
    effective = {key:weights[key]/total for key in available} if total else {}
    score = sum(effective[key]*value for key,value in available.items()) if effective else None
    return score, effective, missing


def latest_assessments(db: Session, complex_id: str) -> dict[str, RiskAssessment]:
    rows = db.scalars(
        select(RiskAssessment)
        .where(RiskAssessment.complex_id == complex_id)
        .order_by(RiskAssessment.assessed_at.desc())
    ).all()
    result: dict[str, RiskAssessment] = {}
    for row in rows:
        result.setdefault(row.assessment_type, row)
    return result


def profile_payload(profile: SeoulComplexProfile, assessments: dict[str, RiskAssessment]) -> dict:
    def assessment(kind: str) -> dict | None:
        item = assessments.get(kind)
        if not item:
            return None
        return {
            "assessment_id": item.assessment_id,
            "assessment_type": item.assessment_type,
            "score": item.score,
            "grade": item.grade,
            "method_type": item.method_type,
            "method_version": item.method_version,
            "features": item.feature_snapshot,
            "explanation": item.explanation_snapshot,
            "data_quality_status": item.data_quality_status,
            "assessed_at": item.assessed_at,
        }

    return {
        "complex_id": profile.complex_id,
        "complex_name": profile.complex_name,
        "address": profile.address,
        "normalized_address": profile.normalized_address,
        "latitude": profile.latitude,
        "longitude": profile.longitude,
        "district": profile.district,
        "household_count": profile.household_count,
        "building_count": profile.building_count,
        "completion_date": profile.completion_date,
        "building_age_years": profile.building_age_years,
        "kapt_code": profile.kapt_code,
        "analysis_eligible": profile.analysis_eligible,
        "eligibility_reason": profile.eligibility_reason,
        "validation_status": profile.validation_status,
        "source_name": profile.source_name,
        "data_version": profile.data_version,
        "updated_at": profile.updated_at,
        "assessments": {kind: assessment(kind) for kind in (
            "flood_susceptibility", "historical_exposure", "drainage_infrastructure_context", "dynamic_climate_stress", "climate_vulnerability",
            "facility_vulnerability", "data_confidence", "resilience"
        )},
    }


def run_stress_test(db: Session, complex_id: str, rain_change_pct: float, sewer_change_pct: float) -> StressTestRun:
    profile = db.get(SeoulComplexProfile, complex_id)
    if not profile:
        raise LookupError("서울 분석 대상 단지가 아닙니다")
    assessments = latest_assessments(db, complex_id)
    climate = assessments.get("climate_vulnerability")
    dynamic = assessments.get("dynamic_climate_stress")
    now = datetime.now(UTC)
    if not climate or climate.score is None or not dynamic:
        run = StressTestRun(
            run_id=uuid.uuid4().hex, complex_id=complex_id,
            scenario_type=f"rain_{rain_change_pct:+g}_sewer_{sewer_change_pct:+g}",
            base_features={}, modified_features={}, base_score=None, scenario_score=None,
            method_version="scenario-feature-only-v2", data_quality_status="NOT_READY", created_at=now,
        )
    else:
        base = dict(dynamic.feature_snapshot or {})
        modified = dict(base)
        for key in ("rain_1h_mm", "rain_3h_mm", "rain_6h_mm", "rain_24h_mm"):
            if base.get(key) is not None:
                modified[key] = round(float(base[key]) * (1 + rain_change_pct / 100), 4)
        if base.get("sewer_level_current") is not None:
            modified["sewer_level_current"] = round(float(base["sewer_level_current"]) * (1 + sewer_change_pct / 100), 4)
        run = StressTestRun(
            run_id=uuid.uuid4().hex, complex_id=complex_id,
            scenario_type=f"rain_{rain_change_pct:+g}_sewer_{sewer_change_pct:+g}",
            base_features=base, modified_features=modified, base_score=climate.score,
            scenario_score=None, method_version="scenario-feature-only-v2",
            data_quality_status="NOT_READY", created_at=now,
        )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def load_weights() -> dict:
    return json.loads((ROOT / "config" / "resilience_weights.json").read_text(encoding="utf-8"))
