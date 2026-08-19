from __future__ import annotations

import hashlib
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


def load_flood_traces(paths: list[Path]) -> gpd.GeoDataFrame:
    frames: list[gpd.GeoDataFrame] = []
    for path in paths:
        frame = gpd.read_parquet(path)
        if frame.crs is None:
            raise ValueError(f"침수흔적도 CRS 누락: {path}")
        frames.append(frame.to_crs("EPSG:5179"))
    if not frames:
        raise FileNotFoundError("적재된 침수흔적도 GeoParquet이 없습니다.")
    combined = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True),
        geometry="geometry",
        crs="EPSG:5179",
    )
    if "source_year" not in combined and "event_year" in combined:
        combined["source_year"] = combined["event_year"]
    return combined[combined.geometry.notna() & ~combined.geometry.is_empty].copy()


def flood_data_version(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode("utf-8"))
        digest.update(str(path.stat().st_size).encode())
        digest.update(str(path.stat().st_mtime_ns).encode())
    return digest.hexdigest()


def _years(frame: gpd.GeoDataFrame, geometry) -> list[int]:
    candidates = frame.iloc[list(frame.sindex.query(geometry, predicate="intersects"))]
    return sorted({int(year) for year in candidates["source_year"].dropna()})


def _count(frame: gpd.GeoDataFrame, geometry) -> int:
    return int(frame.sindex.query(geometry, predicate="intersects").size)


def _overlap_ratio(frame: gpd.GeoDataFrame, buffer) -> float:
    candidates = frame.iloc[list(frame.sindex.query(buffer, predicate="intersects"))]
    if candidates.empty:
        return 0.0
    covered = candidates.geometry.intersection(buffer).union_all().area
    return round(min(1.0, float(covered / buffer.area)), 6)


def _depth_statistics(frame: gpd.GeoDataFrame, geometry) -> dict[str, float | int | None]:
    indexes = list(frame.sindex.query(geometry, predicate="intersects"))
    nearby = frame.iloc[indexes]
    if "flood_depth" not in nearby:
        return {"count": 0, "max_m": None, "mean_m": None}
    values = pd.to_numeric(nearby["flood_depth"], errors="coerce").dropna()
    if values.empty:
        return {"count": 0, "max_m": None, "mean_m": None}
    return {
        "count": int(values.size),
        "max_m": round(float(values.max()), 3),
        "mean_m": round(float(values.mean()), 3),
    }


def analyze_complex(frame: gpd.GeoDataFrame, longitude: float, latitude: float) -> dict:
    point = gpd.GeoSeries([Point(longitude, latitude)], crs="EPSG:4326").to_crs("EPSG:5179").iloc[0]
    buffers = {radius:point.buffer(radius) for radius in (100, 300, 500)}
    nearby_indexes = list(frame.sindex.query(buffers[500], predicate="intersects"))
    nearby = frame.iloc[nearby_indexes]
    nearest = None if nearby.empty else float(nearby.geometry.distance(point).min())
    depth = {radius: _depth_statistics(frame, buffer) for radius, buffer in buffers.items()}
    return {
        "nearest_trace_distance_m":None if nearest is None else round(nearest, 2),
        "intersects_trace":bool(frame.sindex.query(point, predicate="intersects").size),
        **{f"trace_count_{radius}m":_count(frame, buffer) for radius,buffer in buffers.items()},
        **{f"overlap_ratio_{radius}m":_overlap_ratio(frame, buffer) for radius,buffer in buffers.items()},
        "hit_years_point":_years(frame, point),
        **{f"hit_years_{radius}m":_years(frame, buffer) for radius,buffer in buffers.items()},
        **{f"flood_depth_{radius}m": values for radius, values in depth.items()},
    }


def historical_exposure_index(feature) -> float:
    """Transparent proximity index; it is not a flood probability."""
    distance = feature.nearest_trace_distance_m
    if feature.intersects_trace:
        base = 100.0
    elif distance is None or distance > 500:
        base = 0.0
    elif distance <= 100:
        base = 75.0
    elif distance <= 300:
        base = 50.0
    else:
        base = 25.0
    recurrence = max(0, len(feature.hit_years_100m) - 1) * 5
    return min(100.0, base + recurrence)
