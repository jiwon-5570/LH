from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.app.collectors.registry import get_dataset
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

API_DATASETS = (
    "seoul_flood_forecast_geometry",
    "seoul_rain_gauge_locations",
    "seoul_pump_station_attributes",
    "seoul_river_levels",
)


def api_configuration_status() -> dict[str, dict]:
    """Report configuration presence without exposing credentials."""
    result: dict[str, dict] = {}
    for dataset_id in API_DATASETS:
        spec = get_dataset(dataset_id)
        key_configured = bool(os.getenv(spec.api_key_env or "", "").strip())
        url_configured = bool(os.getenv(spec.api_url_env or "", "").strip())
        result[dataset_id] = {
            "api_key_env": spec.api_key_env,
            "api_url_env": spec.api_url_env,
            "api_key_configured": key_configured,
            "api_url_configured": url_configured,
            "collection_ready": key_configured and url_configured,
        }
    return result


def _files(directory: Path, pattern: str) -> list[Path]:
    return sorted(path for path in directory.glob(pattern) if not path.name.endswith("statistics.parquet"))


def _version(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode())
        digest.update(str(path.stat().st_size).encode())
        digest.update(str(path.stat().st_mtime_ns).encode())
    return digest.hexdigest()


def _load_geodata(paths: list[Path]) -> gpd.GeoDataFrame | None:
    frames: list[gpd.GeoDataFrame] = []
    for path in paths:
        columns = pd.read_parquet(path).columns
        if "geometry" not in columns:
            continue
        frames.append(gpd.read_parquet(path))
    if not frames:
        return None
    if any(frame.crs is None for frame in frames):
        raise ValueError("Processed spatial dataset is missing CRS")
    return gpd.GeoDataFrame(
        pd.concat([frame.to_crs("EPSG:5179") for frame in frames], ignore_index=True),
        geometry="geometry", crs="EPSG:5179",
    )


def _nearest(frame: gpd.GeoDataFrame | None, point, id_column: str, name_column: str) -> dict:
    if frame is None or frame.empty:
        return {"id": None, "name": None, "distance_m": None}
    distances = frame.geometry.distance(point)
    index = distances.idxmin()
    row = frame.loc[index]
    return {
        "id": None if pd.isna(row.get(id_column)) else str(row.get(id_column)),
        "name": None if pd.isna(row.get(name_column)) else str(row.get(name_column)),
        "distance_m": round(float(distances.loc[index]), 2),
    }


def _expected_flood(frame: gpd.GeoDataFrame | None, point) -> dict:
    if frame is None or frame.empty:
        return {}
    result: dict = {"expected_flood_overlap": bool(frame.sindex.query(point, predicate="intersects").size)}
    stages: list[float] = []
    for radius in (100, 300, 500):
        buffer = point.buffer(radius)
        indexes = list(frame.sindex.query(buffer, predicate="intersects"))
        nearby = frame.iloc[indexes]
        covered = 0.0 if nearby.empty else nearby.geometry.intersection(buffer).union_all().area
        result[f"expected_flood_area_ratio_{radius}m"] = round(min(1.0, float(covered / buffer.area)), 6)
        if "flood_stage" in nearby:
            stages.extend(pd.to_numeric(nearby["flood_stage"], errors="coerce").dropna().tolist())
    result["expected_flood_max_stage"] = max(stages) if stages else None
    return result


def _pump_capacity(pumps: gpd.GeoDataFrame | None, attributes: pd.DataFrame | None, point) -> dict:
    if pumps is None or attributes is None or pumps.empty or attributes.empty:
        return {"nearby_total_pump_capacity_1km": None}
    id_column = "pump_station_id" if "pump_station_id" in attributes else "pump_id"
    pump_id_column = "pump_id" if "pump_id" in pumps else "pump_station_id"
    if id_column in attributes and pump_id_column in pumps:
        merged = pumps.merge(attributes, left_on=pump_id_column, right_on=id_column, how="left")
    elif "pump_name" in pumps and "pump_station_name" in attributes:
        merged = pumps.assign(_join=pumps["pump_name"].astype(str).str.replace(" ", ""))
        attrs = attributes.assign(_join=attributes["pump_station_name"].astype(str).str.replace(" ", ""))
        merged = merged.merge(attrs, on="_join", how="left")
    else:
        return {"nearby_total_pump_capacity_1km": None}
    if "pump_capacity" not in merged:
        return {"nearby_total_pump_capacity_1km": None}
    nearby = merged.loc[merged.geometry.distance(point) <= 1000]
    values = pd.to_numeric(nearby["pump_capacity"], errors="coerce").dropna()
    return {"nearby_total_pump_capacity_1km": None if values.empty else round(float(values.sum()), 3)}


def dataset_availability(root: Path = ROOT) -> dict[str, dict]:
    flood = _files(root / "data/processed/mois_flood_trace", "*.parquet")
    pump = _files(root / "data/processed/seoul_rain_pump", "*.parquet")
    rain = _files(root / "data/processed/seoul_rainfall_history", "**/*.parquet")
    rain = [path for path in rain if path.name != "station_year_statistics.parquet"]
    present: dict[str, list[Path]] = {
        "seoul_flood_trace": flood,
        "seoul_rain_pump_stations": pump,
        "seoul_rainfall_historical": rain,
    }
    for dataset_id in CANONICAL_DATASETS:
        if dataset_id not in present:
            present[dataset_id] = _files(
                root / "data/processed" / dataset_id, "**/*.parquet"
            )
    result: dict[str, dict] = {}
    for dataset_id in CANONICAL_DATASETS:
        paths = present.get(dataset_id, [])
        spatial_expected = dataset_id in {
            "seoul_flood_trace", "seoul_flood_forecast_geometry",
            "seoul_rain_gauge_locations", "seoul_rain_pump_stations",
        }
        geometry_available = False
        if paths and spatial_expected:
            geometry_available = any("geometry" in pd.read_parquet(path).columns for path in paths)
        status = "AVAILABLE" if paths else "BLOCKED_BY_DATA"
        if paths and spatial_expected and not geometry_available:
            status = "PARTIAL_NO_GEOMETRY"
        result[dataset_id] = {
            "status": status,
            "file_count": len(paths),
            "data_version": _version(paths) if paths else None,
            "storage": "GeoParquet/Parquet" if paths else None,
            "geometry_available": geometry_available if spatial_expected else None,
        }
    return result


def build_flood_spatial_features(db: Session, root: Path = ROOT) -> dict:
    availability = dataset_availability(root)
    flood_paths = _files(root / "data/processed/mois_flood_trace", "*.parquet")
    pump_paths = _files(root / "data/processed/seoul_rain_pump", "*.parquet")
    floods = load_flood_traces(flood_paths) if flood_paths else None
    pumps = gpd.read_parquet(pump_paths[-1]).to_crs("EPSG:5179") if pump_paths else None
    forecast = _load_geodata(_files(root / "data/processed/seoul_flood_forecast_geometry", "**/*.parquet")[-1:])
    rain_gauges = _load_geodata(_files(root / "data/processed/seoul_rain_gauge_locations", "**/*.parquet")[-1:])
    river_stations = _load_geodata(_files(root / "data/processed/seoul_river_levels", "**/*.parquet")[-1:])
    attribute_paths = _files(root / "data/processed/seoul_pump_station_attributes", "**/*.parquet")[-1:]
    pump_attributes = pd.concat([pd.read_parquet(path) for path in attribute_paths], ignore_index=True) if attribute_paths else None
    now = datetime.now(UTC)
    version = _version(flood_paths + pump_paths)
    db.execute(delete(FloodSpatialFeature))
    built = coordinate_blocked = 0
    for profile in db.query(SeoulComplexProfile).all():
        has_coordinates = profile.latitude is not None and profile.longitude is not None
        history = analyze_flood(floods, profile.longitude, profile.latitude) if has_coordinates and floods is not None else {}
        pump = analyze_pumps(pumps, profile.longitude, profile.latitude) if has_coordinates and pumps is not None else {}
        point = gpd.GeoSeries([Point(profile.longitude, profile.latitude)], crs="EPSG:4326").to_crs("EPSG:5179").iloc[0] if has_coordinates else None
        expected = _expected_flood(forecast, point) if point is not None else {}
        rain_station = _nearest(rain_gauges, point, "station_id", "station_name") if point is not None else {}
        river_station = _nearest(river_stations, point, "river_station_id", "river_station_name") if point is not None else {}
        capacity = _pump_capacity(pumps, pump_attributes, point) if point is not None else {}
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
            expected_flood_overlap=expected.get("expected_flood_overlap"),
            expected_flood_area_ratio_100m=expected.get("expected_flood_area_ratio_100m"),
            expected_flood_area_ratio_300m=expected.get("expected_flood_area_ratio_300m"),
            expected_flood_area_ratio_500m=expected.get("expected_flood_area_ratio_500m"),
            expected_flood_max_stage=expected.get("expected_flood_max_stage"),
            distance_to_nearest_pump_station_m=pump.get("nearest_pump_distance_m"),
            pump_station_count_500m=pump.get("pump_count_500m"),
            pump_station_count_1km=pump.get("pump_count_1km"),
            pump_station_count_2km=pump.get("pump_count_2km"),
            nearby_total_pump_capacity_1km=capacity.get("nearby_total_pump_capacity_1km"),
            nearest_rain_station_id=rain_station.get("id"),
            rain_station_distance_m=rain_station.get("distance_m"),
            nearest_river_station_id=river_station.get("id"),
            river_station_distance_m=river_station.get("distance_m"),
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
