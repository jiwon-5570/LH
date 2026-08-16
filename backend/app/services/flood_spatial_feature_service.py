from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.app.db.base import FloodSpatialFeature, SeoulComplexProfile
from backend.app.services.historical_flood_service import analyze_complex as analyze_flood
from backend.app.services.historical_flood_service import load_flood_traces
from backend.app.services.rain_pump_service import analyze_complex as analyze_pumps

ROOT = Path(__file__).resolve().parents[3]

CANONICAL_DATASETS = (
    "seoul_flood_trace",
    "seoul_flood_forecast_geometry",
    "seoul_rain_gauge_locations",
    "seoul_rain_pump_stations",
    "seoul_pump_station_attributes",
    "seoul_river_levels",
    "seoul_rainfall_historical",
)


def _files(directory: Path, pattern: str) -> list[Path]:
    return sorted(path for path in directory.glob(pattern) if not path.name.endswith("statistics.parquet"))


def _version(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode())
        digest.update(str(path.stat().st_size).encode())
        digest.update(str(path.stat().st_mtime_ns).encode())
    return digest.hexdigest()


def dataset_availability(root: Path = ROOT) -> dict[str, dict]:
    flood = _files(root / "data/processed/mois_flood_trace", "*.parquet")
    pump = _files(root / "data/processed/seoul_rain_pump", "*.parquet")
    rain = _files(root / "data/processed/seoul_rainfall_history", "**/*.parquet")
    rain = [path for path in rain if path.name != "station_year_statistics.parquet"]
    present = {
        "seoul_flood_trace": flood,
        "seoul_rain_pump_stations": pump,
        "seoul_rainfall_historical": rain,
    }
    result: dict[str, dict] = {}
    for dataset_id in CANONICAL_DATASETS:
        paths = present.get(dataset_id, [])
        result[dataset_id] = {
            "status": "AVAILABLE" if paths else "BLOCKED_BY_DATA",
            "file_count": len(paths),
            "data_version": _version(paths) if paths else None,
            "storage": "GeoParquet/Parquet" if paths else None,
        }
    return result


def build_flood_spatial_features(db: Session, root: Path = ROOT) -> dict:
    availability = dataset_availability(root)
    flood_paths = _files(root / "data/processed/mois_flood_trace", "*.parquet")
    pump_paths = _files(root / "data/processed/seoul_rain_pump", "*.parquet")
    floods = load_flood_traces(flood_paths) if flood_paths else None
    pumps = gpd.read_parquet(pump_paths[-1]).to_crs("EPSG:5179") if pump_paths else None
    now = datetime.now(UTC)
    version = _version(flood_paths + pump_paths)
    db.execute(delete(FloodSpatialFeature))
    built = coordinate_blocked = 0
    for profile in db.query(SeoulComplexProfile).all():
        has_coordinates = profile.latitude is not None and profile.longitude is not None
        history = analyze_flood(floods, profile.longitude, profile.latitude) if has_coordinates and floods is not None else {}
        pump = analyze_pumps(pumps, profile.longitude, profile.latitude) if has_coordinates and pumps is not None else {}
        years = history.get("hit_years_500m", [])
        statuses = {key: value["status"] for key, value in availability.items()}
        if not has_coordinates:
            statuses["complex_coordinates"] = "BLOCKED_BY_DATA"
            coordinate_blocked += 1
        else:
            statuses["complex_coordinates"] = "AVAILABLE"
        available_count = sum(value == "AVAILABLE" for key, value in statuses.items() if key != "complex_coordinates")
        quality = "COMPLETE" if available_count == len(CANONICAL_DATASETS) else "PARTIAL"
        db.add(FloodSpatialFeature(
            complex_id=profile.complex_id,
            historical_flood_overlap=history.get("intersects_trace"),
            historical_flood_count_100m=history.get("trace_count_100m"),
            historical_flood_count_300m=history.get("trace_count_300m"),
            historical_flood_count_500m=history.get("trace_count_500m"),
            historical_flood_area_ratio_100m=history.get("overlap_ratio_100m"),
            historical_flood_area_ratio_300m=history.get("overlap_ratio_300m"),
            historical_flood_area_ratio_500m=history.get("overlap_ratio_500m"),
            last_flood_year=max(years) if years else None,
            expected_flood_overlap=None,
            expected_flood_area_ratio_100m=None,
            expected_flood_area_ratio_300m=None,
            expected_flood_area_ratio_500m=None,
            expected_flood_max_stage=None,
            distance_to_nearest_pump_station_m=pump.get("nearest_pump_distance_m"),
            pump_station_count_500m=pump.get("pump_count_500m"),
            pump_station_count_1km=pump.get("pump_count_1km"),
            pump_station_count_2km=pump.get("pump_count_2km"),
            nearby_total_pump_capacity_1km=None,
            nearest_rain_station_id=None,
            rain_station_distance_m=None,
            nearest_river_station_id=None,
            river_station_distance_m=None,
            dataset_statuses=statuses,
            source_metadata=availability,
            data_version=version,
            processed_at=now,
            data_quality_status=quality if has_coordinates else "INSUFFICIENT",
        ))
        built += 1
    db.commit()
    return {
        "features": built,
        "coordinate_blocked": coordinate_blocked,
        "dataset_availability": availability,
        "data_version": version,
        "processed_at": now.isoformat(),
    }


def feature_payload(item: FloodSpatialFeature | None, section: str | None = None) -> dict:
    if item is None:
        return {"status": "NOT_READY", "reason": "flood_spatial_features has not been built"}
    values = {column.name: getattr(item, column.name) for column in item.__table__.columns}
    if section is None:
        return values
    prefixes = {
        "flood-history": ("historical_", "last_flood_year"),
        "flood-forecast": ("expected_",),
        "rainfall": ("nearest_rain_", "rain_station_"),
        "drainage": ("distance_to_nearest_pump_", "pump_station_", "nearby_total_pump_"),
        "river": ("nearest_river_", "river_station_"),
    }[section]
    filtered = {key: value for key, value in values.items() if key.startswith(prefixes)}
    dataset_map = {
        "flood-history": ["seoul_flood_trace"],
        "flood-forecast": ["seoul_flood_forecast_geometry"],
        "rainfall": ["seoul_rain_gauge_locations", "seoul_rainfall_historical"],
        "drainage": ["seoul_rain_pump_stations", "seoul_pump_station_attributes"],
        "river": ["seoul_river_levels"],
    }
    filtered["datasets"] = {
        key: item.source_metadata.get(key, {}) for key in dataset_map[section]
    }
    filtered["data_quality_status"] = item.data_quality_status
    filtered["processed_at"] = item.processed_at
    return filtered
