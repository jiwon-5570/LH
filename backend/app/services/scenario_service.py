from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import SeoulComplexProfile, StressTestRun
from backend.app.services.seoul_resilience_service import (
    latest_assessments,
    load_weights,
    renormalized_vulnerability,
    resilience_grade,
)

METHOD_TYPE = "composite_scenario"
METHOD_VERSION = "scenario-baseline-v1"


def _finite(value: float | None) -> float | None:
    if value is None:
        return None
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("시나리오 입력은 유한한 숫자여야 합니다")
    return value


def _changed(value: object, pct: float) -> float | None:
    if value is None:
        return None
    return round(float(value) * (1 + pct / 100), 4)


def run_complex_scenario(db: Session, profile: SeoulComplexProfile, scenario_id: str, scenario_name: str,
                         rain_change_pct: float, sewer_change_pct: float, river_change_pct: float,
                         absolute_rain: dict[str, float | None] | None = None) -> dict:
    assessments = latest_assessments(db, profile.complex_id)
    dynamic = assessments.get("dynamic_climate_stress")
    climate = assessments.get("climate_vulnerability")
    resilience = assessments.get("resilience")
    confidence = assessments.get("data_confidence")
    if not dynamic or dynamic.score is None or not climate or climate.score is None or not resilience or resilience.score is None:
        return {"complex_id": profile.complex_id, "complex_name": profile.complex_name,
                "latitude": profile.latitude, "longitude": profile.longitude, "scenario_resilience_score": None,
                "data_confidence": confidence.score if confidence else None, "error": "동적 또는 회복력 Feature 부족"}

    base_dynamic = dict(dynamic.feature_snapshot or {})
    scenario_dynamic = dict(base_dynamic)
    for key in ("rain_1h_mm", "rain_3h_mm", "rain_6h_mm", "rain_24h_mm"):
        explicit = (absolute_rain or {}).get(key)
        scenario_dynamic[key] = _finite(explicit) if explicit is not None else _changed(base_dynamic.get(key), rain_change_pct)
    scenario_dynamic["sewer_level_current"] = _changed(base_dynamic.get("sewer_level_current"), sewer_change_pct)
    scenario_dynamic["river_level_current"] = _changed(base_dynamic.get("river_level_current"), river_change_pct)
    scenario_dynamic.update({"scenario_input": True, "source": "USER_SCENARIO",
                             "rain_change_pct": rain_change_pct, "sewer_change_pct": sewer_change_pct,
                             "river_change_pct": river_change_pct})

    base_rain_factor = base_dynamic.get("rain_1h_empirical_index")
    rain_factor = min(100.0, max(0.0, float(base_rain_factor) * (1 + rain_change_pct / 100))) if base_rain_factor is not None else None
    base_sewer = base_dynamic.get("sewer_level_current")
    sewer_factor = min(100.0, max(0.0, float(dynamic.score) * (1 + sewer_change_pct / 100))) if base_sewer is not None else None
    base_river = base_dynamic.get("river_level_current")
    river_factor = min(100.0, max(0.0, float(dynamic.score) * (1 + river_change_pct / 100))) if base_river is not None else None
    dynamic_parts = [x for x in (rain_factor, sewer_factor, river_factor) if x is not None]
    scenario_dynamic_score = sum(dynamic_parts) / len(dynamic_parts) if dynamic_parts else None

    climate_features = dict(climate.feature_snapshot or {})
    static_flood = climate_features.get("static_flood_susceptibility")
    scenario_climate, _, _ = renormalized_vulnerability(
        {"static_flood_susceptibility": static_flood, "dynamic_climate_stress": scenario_dynamic_score},
        {"static_flood_susceptibility": .55, "dynamic_climate_stress": .45},
    )
    res_features = dict(resilience.feature_snapshot or {})
    confidence_score = confidence.score if confidence and confidence.score is not None else res_features.get("data_confidence")
    component_values = {
        "climate_vulnerability": scenario_climate,
        "terrain_drainage_vulnerability": res_features.get("terrain_drainage_vulnerability"),
        "facility_vulnerability": res_features.get("facility_vulnerability"),
        "historical_exposure": res_features.get("historical_exposure"),
        "data_uncertainty": None if confidence_score is None else 100 - float(confidence_score),
    }
    vulnerability, _, _ = renormalized_vulnerability(component_values, load_weights()["weights"])
    scenario_score = None if vulnerability is None else round(100 - vulnerability, 2)
    base_score = float(resilience.score)
    base_climate = float(climate.score)
    top_changed = sorted([
        {"factor": "강우", "change_pct": rain_change_pct},
        {"factor": "하수관 수위", "change_pct": sewer_change_pct},
        {"factor": "하천 수위", "change_pct": river_change_pct},
    ], key=lambda x: abs(x["change_pct"]), reverse=True)
    now = datetime.now(UTC)
    run = StressTestRun(run_id=f"{scenario_id}:{profile.complex_id}", complex_id=profile.complex_id,
        scenario_type=scenario_name, base_features={"dynamic": base_dynamic, "climate": climate_features, "resilience": res_features},
        modified_features={"dynamic": scenario_dynamic, "scenario_input": True, "source": "USER_SCENARIO",
                           "method_type": METHOD_TYPE, "top_changed_factors": top_changed},
        base_score=base_score, scenario_score=scenario_score, method_version=METHOD_VERSION,
        data_quality_status="COMPLETE" if scenario_score is not None else "NOT_READY", created_at=now)
    db.add(run)
    return {"complex_id": profile.complex_id, "complex_name": profile.complex_name, "latitude": profile.latitude,
            "longitude": profile.longitude, "base_resilience_score": base_score,
            "scenario_resilience_score": scenario_score, "resilience_delta": None if scenario_score is None else round(scenario_score-base_score, 2),
            "base_climate_vulnerability": base_climate, "scenario_climate_vulnerability": scenario_climate,
            "climate_delta": None if scenario_climate is None else round(scenario_climate-base_climate, 2),
            "base_dynamic_stress": dynamic.score, "scenario_dynamic_stress": scenario_dynamic_score,
            "base_grade": resilience_grade(base_score), "scenario_grade": resilience_grade(scenario_score),
            "top_changed_factors": top_changed, "data_confidence": confidence_score,
            "base_features": base_dynamic, "scenario_features": scenario_dynamic, "error": None}


def _summary(results: list[dict], scenario: bool) -> dict:
    key = "scenario_resilience_score" if scenario else "base_resilience_score"
    scores = [float(r[key]) for r in results if r.get(key) is not None]
    return {"total": len(results), "complete": len(scores), "insufficient": len(results)-len(scores),
            "vulnerable": sum(x <= 39 for x in scores), "caution": sum(39 < x <= 59 for x in scores),
            "average_resilience_score": round(sum(scores)/len(scores), 2) if scores else None}


def run_citywide_scenario(db: Session, payload) -> dict:
    scenario_id = uuid.uuid4().hex
    profiles = db.scalars(select(SeoulComplexProfile).where(SeoulComplexProfile.analysis_eligible.is_(True))).all()
    targets = profiles if payload.apply_to_all_complexes else [p for p in profiles if p.complex_id == payload.target_complex_id]
    absolute = {k: getattr(payload, k) for k in ("rain_1h_mm", "rain_3h_mm", "rain_6h_mm", "rain_24h_mm")}
    name = payload.scenario_name or f"강우 {payload.rain_change_pct:+g}% · 하수 {payload.sewer_change_pct:+g}% · 하천 {payload.river_change_pct:+g}%"
    results = [run_complex_scenario(db, p, scenario_id, name, payload.rain_change_pct,
        payload.sewer_change_pct, payload.river_change_pct, absolute) for p in targets]
    db.commit()
    return {"scenario_id": scenario_id, "scenario_name": name, "created_at": datetime.now(UTC),
            "method_type": METHOD_TYPE, "method_version": METHOD_VERSION, "scenario_input": True,
            "source": "USER_SCENARIO", "base_summary": _summary(results, False),
            "scenario_summary": _summary(results, True), "complex_results": results}


def compare_realtime_scenario(result: dict) -> dict:
    return {"base": result.get("base_resilience_score"), "scenario": result.get("scenario_resilience_score"),
            "delta": result.get("resilience_delta"), "top_changed_factors": result.get("top_changed_factors", [])}
