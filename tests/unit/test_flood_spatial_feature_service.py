from pathlib import Path

from backend.app.services.flood_spatial_feature_service import (
    CANONICAL_DATASETS,
    dataset_availability,
    feature_payload,
)


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
