from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from backend.app.services.flood_spatial_feature_service import (
    CANONICAL_DATASETS,
    _pump_capacity,
    dataset_availability,
    feature_payload,
)


def test_pump_capacity_joins_string_and_numeric_official_ids():
    pumps = gpd.GeoDataFrame(
        {"pump_id": ["12"], "pump_name": ["테스트펌프장"]},
        geometry=[Point(0, 0)],
        crs="EPSG:5179",
    )
    attributes = pd.DataFrame(
        {"pump_station_id": [12.0], "pump_station_name": ["테스트펌프장"], "pump_capacity": [42.5]}
    )
    assert _pump_capacity(pumps, attributes, Point(10, 0))["nearby_total_pump_capacity_1km"] == 42.5


def test_availability_never_invents_missing_sources(tmp_path: Path):
    availability = dataset_availability(tmp_path)
    assert set(availability) == set(CANONICAL_DATASETS)
    assert all(item["status"] == "BLOCKED_BY_DATA" for item in availability.values())
    assert all(item["data_version"] is None for item in availability.values())


def test_missing_feature_is_explicitly_not_ready():
    assert feature_payload(None) == {
        "status": "NOT_READY",
        "reason": "flood_spatial_features has not been built",
    }


def test_availability_detects_new_api_parquet(tmp_path: Path):
    target = tmp_path / "data/processed/seoul_river_levels"
    target.mkdir(parents=True)
    (target / "api.parquet").write_bytes(b"verified-test-artifact")
    availability = dataset_availability(tmp_path)
    assert availability["seoul_river_levels"]["status"] == "AVAILABLE"
    assert availability["seoul_river_levels"]["file_count"] == 1
