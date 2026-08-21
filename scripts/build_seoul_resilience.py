"""Build Seoul profiles and transparent baseline assessments from real ingested data."""

from __future__ import annotations

import json
import math
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import rasterio
from pyproj import Transformer
from sqlalchemy import delete

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.base import (
    Base,
    ComplexDataLink,
    FloodSpatialFeature,
    HistoricalFloodFeature,
    ModelVersion,
    RainPumpProximityFeature,
    RiskAssessment,
    SeoulComplexProfile,
    TerrainFeature,
)
from backend.app.db.session import SessionLocal, engine
from backend.app.services.flood_spatial_feature_service import build_flood_spatial_features
from backend.app.services.historical_flood_service import historical_exposure_index
from backend.app.services.rainfall_history_service import empirical_rain_index
from backend.app.services.seoul_resilience_service import (
    confidence_level,
    coordinate_in_seoul_extent,
    is_seoul_address,
    normalize_address,
    renormalized_vulnerability,
    resilience_grade,
    risk_grade,
)

NOW = datetime.now(UTC)


def latest_parquet(dataset_id: str) -> Path | None:
    paths = list((ROOT / "data" / "processed" / dataset_id).glob("*.parquet"))
    return max(paths, key=lambda path: path.stat().st_mtime) if paths else None


def rainfall_reference() -> dict | None:
    paths = list((ROOT / "data/processed/seoul_rainfall_history").glob("*/rainfall_reference.json"))
    if not paths:
        return None
    return json.loads(max(paths, key=lambda path: path.stat().st_mtime).read_text(encoding="utf-8"))


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
                if (
                    dataset.bounds.left <= x <= dataset.bounds.right
                    and dataset.bounds.bottom <= y <= dataset.bounds.top
                ):
                    value = float(next(dataset.sample([(x, y)]))[0])
                    if (dataset.nodata is None or value != dataset.nodata) and math.isfinite(value):
                        result[row["complex_id"]] = value
                    break
    finally:
        for dataset in datasets:
            dataset.close()
    return result


def observation_summary() -> tuple[dict[str, dict], dict[str, dict], dict[str, dict]]:
    rain: dict[str, dict] = {}
    rain_by_station: dict[str, dict] = {}
    sewer: dict[str, dict] = {}
    rain_path = latest_parquet("seoul_rainfall")
    if rain_path:
        frame = pd.read_parquet(rain_path)
        frame["time"] = pd.to_datetime(frame["observed_at"], errors="coerce", utc=True)
        frame["value"] = pd.to_numeric(frame["rainfall_mm"], errors="coerce")
        valid_rain = frame.dropna(subset=["time", "station_id"])
        valid_rain = valid_rain.assign(station_id=valid_rain["station_id"].astype(str))
        for station_id, group in valid_rain.groupby("station_id"):
            latest = group["time"].max()
            current = group[group["time"] == latest]
            station = str(current.iloc[0].get("station_name", station_id))
            station_rows = group.sort_values("time")
            totals = {}
            coverage = {}
            for minutes in (10, 60, 180, 360, 720, 1440, 2880, 4320):
                window = station_rows[
                    (station_rows["time"] > latest - pd.Timedelta(minutes=minutes)) & (station_rows["time"] <= latest)
                ]
                expected = max(1, minutes // 10)
                actual = int(window["value"].notna().sum())
                ratio = actual / expected
                coverage[minutes] = {"expected": expected, "actual": actual, "coverage_ratio": round(ratio, 4)}
                totals[minutes] = float(window["value"].sum()) if ratio >= 0.8 else None
            indexed = station_rows.set_index("time")["value"].sort_index()
            last_24h = indexed[indexed.index > latest - pd.Timedelta(hours=24)]
            max_1h = last_24h.rolling("60min").sum().max()
            max_3h = last_24h.rolling("180min").sum().max()
            summary = {
                "value": None if current["value"].dropna().empty else float(current["value"].max()),
                "time": latest.to_pydatetime(),
                "station_id": str(station_id),
                "station": station,
                "totals": totals,
                "coverage": coverage,
                "max_rain_1h_24h": None if pd.isna(max_1h) else float(max_1h),
                "max_rain_3h_24h": None if pd.isna(max_3h) else float(max_3h),
            }
            rain_by_station[str(station_id)] = summary
            district = current.iloc[0].get("GU_NM")
            if pd.notna(district):
                previous = rain.get(str(district))
                if previous is None or summary["time"] > previous["time"]:
                    rain[str(district)] = summary
    sewer_path = latest_parquet("seoul_sewer_level")
    if sewer_path:
        frame = pd.read_parquet(sewer_path)
        frame["time"] = pd.to_datetime(frame["observed_at"], errors="coerce", utc=True)
        frame["value"] = pd.to_numeric(frame["water_level"], errors="coerce")
        for district, group in frame.dropna(subset=["SE_NM", "time"]).groupby("SE_NM"):
            latest = group["time"].max()
            current = group[group["time"] == latest]
            sewer[str(district)] = {
                "value": float(current["value"].max() or 0),
                "time": latest.to_pydatetime(),
                "sensor": str(current.iloc[0].get("sensor_id", "")),
                "p95": float(group["value"].quantile(0.95) or 0),
            }
    return rain, rain_by_station, sewer


def add_assessment(
    db,
    complex_id: str,
    kind: str,
    score: float | None,
    method: str,
    version: str,
    features: dict,
    factors: list[dict],
    quality: str,
) -> None:
    db.add(
        RiskAssessment(
            assessment_id=uuid.uuid4().hex,
            complex_id=complex_id,
            assessment_type=kind,
            score=None if score is None else round(max(0, min(100, score)), 2),
            grade=resilience_grade(score)
            if kind == "resilience"
            else (confidence_level(score or 0) if kind == "data_confidence" else risk_grade(score)),
            method_type=method,
            method_version=version,
            feature_snapshot=features,
            explanation_snapshot={"top_factors": factors[:5]},
            data_quality_status=quality,
            assessed_at=NOW,
            valid_from=NOW,
            valid_until=None,
            created_at=NOW,
        )
    )


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
    basic_by_code = (
        {} if kapt_basic.empty else kapt_basic.drop_duplicates("kapt_code").set_index("kapt_code").to_dict("index")
    )
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
        # LH source addresses use all three forms: 서울특별시, 서울시, and 서울.
        # Treat the administrative suffix as optional so district-level rainfall
        # and sewer observations are not dropped solely because of formatting.
        district_match = re.search(r"서울(?:특별시|시)?\s+([^\s]+구)", str(row["address"]))
        district = district_match.group(1) if district_match else None
        match = pd.DataFrame()
        if not kapt_list.empty:
            match = kapt_list[kapt_list["name_key"] == compact(row["complex_name"])]
        kapt_code = str(match.iloc[0]["kapt_code"]) if len(match) == 1 else None
        basic = basic_by_code.get(kapt_code, {}) if kapt_code else {}
        completion, age = date_and_age(row.get("준공일") or basic.get("approval_date"))
        profiles.append(
            {
                "complex_id": cid,
                "complex_name": str(row["complex_name"]),
                "address": str(row["address"]),
                "normalized_address": normalize_address(str(row["address"])),
                "latitude": lat,
                "longitude": lon,
                "district": district,
                "household_count": safe_int(row.get("세대수") or basic.get("households")),
                "building_count": safe_int(row.get("동수") or basic.get("building_count")),
                "completion_date": completion,
                "building_age_years": age,
                "kapt_code": kapt_code,
                "analysis_eligible": eligible,
                "eligibility_reason": "서울 주소 및 좌표 범위 검증"
                if coordinate_ok
                else ("서울 주소 확인; 좌표 미확보" if coordinate_ok is None else "서울 주소와 좌표 범위 불일치"),
                "validation_status": status,
                "source_name": str(row["source_name"]),
                "data_version": str(row["data_version"]),
                "updated_at": NOW,
            }
        )

    with SessionLocal() as db:
        terrain_rows = {row.complex_id: row for row in db.query(TerrainFeature).all()}
        history_rows = {row.complex_id: row for row in db.query(HistoricalFloodFeature).all()}
        rain_pump_rows = {row.complex_id: row for row in db.query(RainPumpProximityFeature).all()}
    elevations = {cid: row.elevation_m for cid, row in terrain_rows.items() if row.elevation_m is not None}
    if not terrain_rows:
        elevations = dem_samples(profiles)
    rain_by_district, rain_by_station, sewer_by_district = observation_summary()
    rain_history = rainfall_reference()
    rain_1h_reference = None if rain_history is None else rain_history.get("references", {}).get("1h")
    weights = json.loads((ROOT / "config" / "resilience_weights.json").read_text(encoding="utf-8"))["weights"]
    with SessionLocal() as db:
        db.execute(delete(RiskAssessment))
        db.execute(delete(SeoulComplexProfile))
        for values in profiles:
            db.add(SeoulComplexProfile(**values))
        db.flush()
        # Build against the freshly normalized profiles so station/pump/river
        # linkage and confidence are from the same reproducible snapshot.
        spatial_summary = build_flood_spatial_features(db)
        flood_spatial_rows = {row.complex_id: row for row in db.query(FloodSpatialFeature).all()}
        for values in profiles:
            cid = values["complex_id"]
            link = links.get(cid)
            elevation = elevations.get(cid)
            terrain = terrain_rows.get(cid)
            terrain_score = (
                terrain.lowland_index_300m if terrain and terrain.data_quality_status == "COMPLETE" else None
            )
            terrain_quality = terrain.data_quality_status if terrain else "INSUFFICIENT"
            terrain_snapshot = (
                {
                    column.name: getattr(terrain, column.name)
                    for column in TerrainFeature.__table__.columns
                    if column.name not in {"terrain_feature_id", "complex_id", "processed_at"}
                }
                if terrain
                else {"elevation_m": elevation}
            )
            if terrain:
                terrain_snapshot["processed_at"] = terrain.processed_at.isoformat()
            terrain_snapshot.update(
                {"flood_trace_status": "BLOCKED_BY_DATA", "expected_flood_geometry_status": "BLOCKED_BY_DATA"}
            )
            history = history_rows.get(cid)
            history_score = historical_exposure_index(history) if history else None
            if history:
                terrain_snapshot["flood_trace_status"] = history.data_quality_status
            rain_pump = rain_pump_rows.get(cid)
            if rain_pump:
                terrain_snapshot["rain_pump_context"] = {
                    "nearest_pump_id": rain_pump.nearest_pump_id,
                    "nearest_pump_name": rain_pump.nearest_pump_name,
                    "nearest_pump_distance_m": rain_pump.nearest_pump_distance_m,
                    "pump_count_1km": rain_pump.pump_count_1km,
                    "pump_count_3km": rain_pump.pump_count_3km,
                    "pump_count_5km": rain_pump.pump_count_5km,
                    "capacity_status": rain_pump.capacity_status,
                    "operation_status": rain_pump.operation_status,
                    "data_version": rain_pump.data_version,
                }
            add_assessment(
                db,
                cid,
                "flood_susceptibility",
                terrain_score,
                "rule_baseline",
                "static-terrain-baseline-v2",
                terrain_snapshot,
                [
                    {
                        "factor": "lowland_index_300m",
                        "label": "300m 주변 대비 저지대 지수",
                        "value": terrain_score,
                        "contribution_points": terrain_score,
                    }
                ],
                terrain_quality,
            )

            history_features = (
                None
                if history is None
                else {
                    "nearest_trace_distance_m": history.nearest_trace_distance_m,
                    "intersects_trace": history.intersects_trace,
                    "overlap_ratio_100m": history.overlap_ratio_100m,
                    "overlap_ratio_300m": history.overlap_ratio_300m,
                    "overlap_ratio_500m": history.overlap_ratio_500m,
                    "hit_years_point": history.hit_years_point,
                    "hit_years_100m": history.hit_years_100m,
                    "hit_years_300m": history.hit_years_300m,
                    "hit_years_500m": history.hit_years_500m,
                    "source_years": history.source_years,
                    "missing_years": history.missing_years,
                    "source_feature_count": history.source_feature_count,
                    "data_version": history.data_version,
                    "not_a_probability": True,
                }
            )
            add_assessment(
                db,
                cid,
                "historical_exposure",
                history_score,
                "rule_evidence",
                "historical-flood-proximity-v1",
                history_features or {},
                [
                    {
                        "factor": "historical_flood_proximity",
                        "label": "공식 침수흔적도 최근접 거리",
                        "value": None if history is None else history.nearest_trace_distance_m,
                        "contribution_points": history_score,
                    }
                ],
                "INSUFFICIENT" if history is None else history.data_quality_status,
            )

            pump_features = (
                {}
                if rain_pump is None
                else terrain_snapshot["rain_pump_context"]
                | {
                    "source_feature_count": rain_pump.source_feature_count,
                    "not_a_capacity_or_protection_score": True,
                }
            )
            add_assessment(
                db,
                cid,
                "drainage_infrastructure_context",
                None,
                "spatial_evidence",
                "rain-pump-proximity-v1",
                pump_features,
                [
                    {
                        "factor": "nearest_rain_pump",
                        "label": "최근접 빗물펌프장 거리",
                        "value": None if rain_pump is None else rain_pump.nearest_pump_distance_m,
                        "contribution_points": None,
                    }
                ],
                "INSUFFICIENT" if rain_pump is None else rain_pump.data_quality_status,
            )

            district = values["district"]
            flood_spatial = flood_spatial_rows.get(cid)
            rain = (
                rain_by_station.get(str(flood_spatial.nearest_rain_station_id))
                if flood_spatial and flood_spatial.nearest_rain_station_id
                else None
            )
            rain_match_method = "station_id_exact" if rain else None
            if rain is None:
                rain = rain_by_district.get(district or "")
                rain_match_method = "district_fallback" if rain else None
            sewer = sewer_by_district.get((district or "").removesuffix("구")) or sewer_by_district.get(district or "")
            rain_age = (NOW - rain["time"]).total_seconds() / 60 if rain else None
            sewer_age = (NOW - sewer["time"]).total_seconds() / 60 if sewer else None
            rain_factor = (
                empirical_rain_index(rain["totals"][60], rain_1h_reference)
                if rain and rain["totals"][60] is not None
                else None
            )
            sewer_factor = min(100.0, (sewer["value"] / sewer["p95"] * 100)) if sewer and sewer["p95"] > 0 else None
            parts = [x for x in (rain_factor, sewer_factor) if x is not None]
            dynamic_score = sum(parts) / len(parts) if parts else None
            dynamic_quality = (
                "STALE"
                if parts and ((rain_age or 10**9) > 180 or (sewer_age or 10**9) > 180)
                else ("PARTIAL" if len(parts) < 2 or rain_match_method == "district_fallback" else "COMPLETE")
            )
            totals = rain["totals"] if rain else {}
            dynamic_features = {
                "rain_10m_mm": totals.get(10),
                "rain_1h_mm": totals.get(60),
                "rain_3h_mm": totals.get(180),
                "rain_6h_mm": totals.get(360),
                "rain_12h_mm": totals.get(720),
                "rain_24h_mm": totals.get(1440),
                "rain_48h_mm": totals.get(2880),
                "rain_72h_mm": totals.get(4320),
                "max_rain_1h_24h": rain.get("max_rain_1h_24h") if rain else None,
                "max_rain_3h_24h": rain.get("max_rain_3h_24h") if rain else None,
                "rain_1h_empirical_index": rain_factor,
                "rain_reference": rain_1h_reference,
                "rain_reference_years": None if rain_history is None else rain_history.get("source_years"),
                "rain_reference_data_version": None if rain_history is None else rain_history.get("data_version"),
                "rain_reference_method": None if rain_history is None else rain_history.get("method"),
                "nearest_rain_station_id": flood_spatial.nearest_rain_station_id if flood_spatial else None,
                "nearest_rain_station_name": (
                    (flood_spatial.source_metadata or {}).get("rain_station_match", {}).get("station_name")
                    if flood_spatial else None
                ),
                "rain_station_distance_m": flood_spatial.rain_station_distance_m if flood_spatial else None,
                "rain_station_match_method": rain_match_method,
                "rain_window_coverage": rain.get("coverage") if rain else None,
                "rain_data_age_minutes": rain_age,
                "sewer_level_current": sewer["value"] if sewer else None,
                "nearest_sewer_sensor_id": sewer["sensor"] if sewer else None,
                "sewer_sensor_distance_m": None,
                "sewer_data_age_minutes": sewer_age,
                "distance_status": "AVAILABLE" if flood_spatial and flood_spatial.rain_station_distance_m is not None else "BLOCKED_BY_DATA",
            }
            add_assessment(
                db,
                cid,
                "dynamic_climate_stress",
                dynamic_score,
                "rule_baseline",
                "dynamic-hydrologic-stress-v2",
                dynamic_features,
                [
                    {
                        "factor": "rain",
                        "label": "최근 강우 관측",
                        "value": rain["value"] if rain else None,
                        "contribution_points": rain_factor,
                    },
                    {
                        "factor": "sewer",
                        "label": "하수관로 수위",
                        "value": sewer["value"] if sewer else None,
                        "contribution_points": sewer_factor,
                    },
                ],
                dynamic_quality,
            )

            climate_values = {"static_flood_susceptibility": terrain_score, "dynamic_climate_stress": dynamic_score}
            climate_score, climate_effective_weights, climate_missing = renormalized_vulnerability(
                climate_values,
                {"static_flood_susceptibility": 0.55, "dynamic_climate_stress": 0.45},
            )
            climate_quality = (
                "INSUFFICIENT" if climate_score is None else ("STALE" if dynamic_quality == "STALE" else "PARTIAL")
            )
            climate_features = climate_values | {
                "available_components": [key for key, value in climate_values.items() if value is not None],
                "missing_components": climate_missing,
                "effective_weights": climate_effective_weights,
            }
            add_assessment(
                db,
                cid,
                "climate_vulnerability",
                climate_score,
                "composite_index",
                "climate-vulnerability-v2",
                climate_features,
                [
                    {
                        "factor": "static",
                        "label": "정적 침수 취약도",
                        "value": terrain_score,
                        "contribution_points": None
                        if terrain_score is None
                        else terrain_score * climate_effective_weights.get("static_flood_susceptibility", 0),
                    },
                    {
                        "factor": "dynamic",
                        "label": "동적 기후 스트레스",
                        "value": dynamic_score,
                        "contribution_points": None
                        if dynamic_score is None
                        else dynamic_score * climate_effective_weights.get("dynamic_climate_stress", 0),
                    },
                ],
                climate_quality,
            )

            elevator_count = int(link.elevator_count if link else 0)
            corrective_count = int(link.corrective_count if link else 0)
            if elevator_count:
                corrective_rate = min(corrective_count / elevator_count, 1)
                facility_score = min(100.0, 12 + (38 if corrective_count else 0) + 42 * corrective_rate)
                facility_quality = "PARTIAL"
            else:
                corrective_rate = None
                facility_score = None
                facility_quality = "INSUFFICIENT"
            add_assessment(
                db,
                cid,
                "facility_vulnerability",
                facility_score,
                "rule_baseline",
                "facility-vulnerability-baseline-v1",
                {
                    "elevator_count": elevator_count,
                    "corrective_action_count": corrective_count,
                    "corrective_rate": corrective_rate,
                    "model_status": "NOT_READY",
                },
                [
                    {
                        "factor": "corrective",
                        "label": "승강기 시정권고 이력",
                        "value": corrective_count,
                        "contribution_points": facility_score,
                    }
                ],
                facility_quality,
            )

            dem_coverage = (
                (terrain.dem_coverage_ratio_100m + terrain.dem_coverage_ratio_300m + terrain.dem_coverage_ratio_500m)
                / 3
                * 100
                if terrain
                else 0
            )
            hydrology_statuses = flood_spatial.dataset_statuses if flood_spatial else {}

            def availability_score(dataset_id: str, statuses=hydrology_statuses) -> float:
                status = statuses.get(dataset_id)
                return {
                    "AVAILABLE": 100.0,
                    "PARTIAL": 60.0,
                    "PARTIAL_NO_GEOMETRY": 45.0,
                    "PARTIAL_NO_LOCATION": 45.0,
                    "REVIEW_REQUIRED": 35.0,
                }.get(status, 0.0)

            components = {
                "coordinate_validation": 100
                if values["validation_status"] == "VALIDATED"
                else 40
                if values["validation_status"] == "ADDRESS_ONLY"
                else 0,
                "dem_coverage": dem_coverage,
                "rain_availability": 100 if rain else 0,
                "rain_freshness": 100 if rain_age is not None and rain_age <= 180 else 0,
                "rainfall_history_availability": 0
                if rain_history is None
                else float(rain_history.get("mean_completeness_ratio", 0)) * 100,
                "sewer_availability": 100 if sewer else 0,
                "sewer_freshness": 100 if sewer_age is not None and sewer_age <= 180 else 0,
                "flood_trace_availability": 80 if history and history.missing_years else 100 if history else 0,
                "flood_forecast_geometry_availability": availability_score("seoul_flood_forecast_geometry"),
                "rain_station_location_availability": availability_score("seoul_rain_gauge_locations"),
                "pump_station_geometry_availability": 100 if rain_pump else 0,
                "pump_station_attribute_availability": availability_score("seoul_pump_station_attributes"),
                "river_level_availability": availability_score("seoul_river_levels"),
                "facility_linkage": 100 if elevator_count else 0,
                "kapt_linkage": 100 if values["kapt_code"] else 0,
            }
            confidence = sum(components.values()) / len(components)
            add_assessment(
                db,
                cid,
                "data_confidence",
                confidence,
                "composite_index",
                "data-confidence-v1",
                components,
                sorted(
                    (
                        {"factor": k, "label": k, "value": v, "contribution_points": v / len(components)}
                        for k, v in components.items()
                    ),
                    key=lambda x: x["value"],
                ),
                confidence_level(confidence),
            )

            component_values = {
                "climate_vulnerability": climate_score,
                "terrain_drainage_vulnerability": terrain_score,
                "facility_vulnerability": facility_score,
                "historical_exposure": history_score,
                "data_uncertainty": 100 - confidence,
            }
            vulnerability, effective_weights, missing = renormalized_vulnerability(component_values, weights)
            available = {key: value for key, value in component_values.items() if value is not None}
            resilience = None if vulnerability is None else 100 - vulnerability
            top = sorted(
                [
                    {
                        "factor": "climate_vulnerability",
                        "label": "기후재난 취약성",
                        "value": climate_score,
                        "contribution_points": None
                        if climate_score is None
                        else weights["climate_vulnerability"] * climate_score,
                    },
                    {
                        "factor": "terrain",
                        "label": "지형·배수 취약성",
                        "value": terrain_score,
                        "contribution_points": None
                        if terrain_score is None
                        else weights["terrain_drainage_vulnerability"] * terrain_score,
                    },
                    {
                        "factor": "facility",
                        "label": "시설 취약성",
                        "value": facility_score,
                        "contribution_points": None
                        if facility_score is None
                        else weights["facility_vulnerability"] * facility_score,
                    },
                    {
                        "factor": "historical_exposure",
                        "label": "공식 침수흔적 근접 이력",
                        "value": history_score,
                        "contribution_points": None
                        if history_score is None
                        else weights["historical_exposure"] * history_score,
                    },
                    {
                        "factor": "data_uncertainty",
                        "label": "데이터 불확실성",
                        "value": 100 - confidence,
                        "contribution_points": weights["data_uncertainty"] * (100 - confidence),
                    },
                ],
                key=lambda x: x["contribution_points"] or -1,
                reverse=True,
            )
            add_assessment(
                db,
                cid,
                "resilience",
                resilience,
                "composite_index",
                "resilience-composite-v3",
                {
                    "climate_vulnerability": climate_score,
                    "terrain_drainage_vulnerability": terrain_score,
                    "facility_vulnerability": facility_score,
                    "historical_exposure": history_score,
                    "data_confidence": confidence,
                    "available_components": list(available),
                    "missing_components": missing,
                    "effective_weights": effective_weights,
                    "not_a_probability": True,
                },
                top,
                confidence_level(confidence),
            )

        for model_id, name, target, reason in (
            (
                "flood-grid-v1",
                "서울 Grid Flood Susceptibility",
                "historical_flood_overlap",
                "침수흔적도 적재 완료; 서울 행정경계·격자 음성표본·시간분리 검증 미완료",
            ),
            (
                "facility-next-inspection-v1",
                "승강기 차기검사 비통과 위험",
                "next_inspection_non_pass",
                "시간순 승강기 연결 학습표 및 외부검증 미완료",
            ),
        ):
            db.merge(
                ModelVersion(
                    model_id=model_id,
                    model_name=name,
                    model_type="classifier",
                    version="v1",
                    target_name=target,
                    training_started_at=None,
                    training_finished_at=None,
                    training_data_version=None,
                    feature_list=[],
                    artifact_path=None,
                    status="BLOCKED_BY_DATA" if model_id.startswith("flood") else "NOT_READY",
                    status_reason=reason,
                    created_at=NOW,
                )
            )
        db.commit()
    print(
        {
            "seoul_profiles": len(profiles),
            "analysis_eligible": sum(x["analysis_eligible"] for x in profiles),
            "coordinate_validated": sum(x["validation_status"] == "VALIDATED" for x in profiles),
            "dem_coverage": len(elevations),
            "flood_spatial_features": spatial_summary["features"],
            "flood_ml": "BLOCKED_BY_DATA",
            "facility_ml": "NOT_READY",
        }
    )


if __name__ == "__main__":
    main()
