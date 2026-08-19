import json
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.collectors.pipeline import _persist_valid_records, _raise_gateway_error, validate
from backend.app.collectors.registry import get_dataset
from backend.app.db.base import Base, DataCollectionRun, SourceRecord


def test_lh_korean_columns_are_normalized():
    frame = pd.DataFrame([{"단지코드":"A1","단지명":"실제단지","주소":"서울특별시","위도":"37.5","경도":"127.0"}])
    valid, quarantine, checks = validate(frame, get_dataset("lh_complexes"))
    assert len(valid) == 1 and quarantine.empty
    assert valid.iloc[0]["complex_id"] == "A1"
    assert all(check["status"] == "pass" for check in checks)

def test_invalid_coordinates_are_quarantined():
    frame = pd.DataFrame([{"단지코드":"A1","단지명":"실제단지","주소":"서울특별시","위도":"0","경도":"0"}])
    valid, quarantine, _ = validate(frame, get_dataset("lh_complexes"))
    assert valid.empty and len(quarantine) == 1


def test_mois_flood_trace_api_aliases_are_normalized():
    frame = pd.DataFrame([{"SN":"101","FLDN_DOWA":"0.8"}])
    valid, quarantine, checks = validate(frame, get_dataset("mois_flood_trace_api"))
    assert quarantine.empty
    assert valid.iloc[0]["trace_serial_number"] == "101"
    assert valid.iloc[0]["flood_depth"] == "0.8"
    assert all(check["status"] == "pass" for check in checks)


def test_mois_gateway_auth_error_is_explicit():
    payload = {"cmmMsgHeader":{"returnAuthMsg":"SERVICE_ACCESS_DENIED_ERROR"}}
    try:
        _raise_gateway_error(payload)
    except RuntimeError as exc:
        assert "SERVICE_ACCESS_DENIED_ERROR" in str(exc)
    else:
        raise AssertionError(json.dumps(payload))


def test_rain_gauge_coordinates_become_verified_geometry():
    frame = pd.DataFrame([
        {"RF_CD":"101", "RF_NM":"서울 관측소", "LAT":"37.55", "LON":"126.98"}
    ])
    valid, quarantine, _ = validate(frame, get_dataset("seoul_rain_gauge_locations"))
    assert quarantine.empty
    assert valid.crs.to_epsg() == 4326
    assert valid.geometry.iloc[0].x == 126.98
    assert valid.geometry.iloc[0].y == 37.55


def test_rain_gauge_history_keeps_latest_station_location():
    frame = pd.DataFrame([
        {"지점":"400", "지점명":"강남", "시작일":"2020-01-01", "종료일":"2023-01-01", "위도":"37.50", "경도":"127.04"},
        {"지점":"400", "지점명":"강남", "시작일":"2023-01-01", "종료일":None, "위도":"37.51", "경도":"127.08"},
    ])
    valid, quarantine, checks = validate(frame, get_dataset("seoul_rain_gauge_locations"))
    assert quarantine.empty
    assert len(valid) == 1
    assert valid.iloc[0]["latitude"] == 37.51
    assert all(check["status"] == "pass" for check in checks)


def test_source_record_preview_is_idempotent(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    spec = get_dataset("seoul_flood_forecast_geometry")
    frame = pd.DataFrame([{"space_id": "A", "flood_stage": 2}])
    collected_at = datetime.now(UTC)
    monkeypatch.setenv("SOURCE_RECORD_SAMPLE_LIMIT", "100")

    with Session(engine) as db:
        for run_id in ("run-1", "run-2"):
            db.add(DataCollectionRun(
                collection_run_id=run_id,
                dataset_id=spec.id,
                source_name=spec.name,
                started_at=collected_at,
                status="running",
            ))
            db.flush()
            _persist_valid_records(db, frame, spec, run_id, "same-version", collected_at)
            db.commit()

        records = db.query(SourceRecord).all()
        assert len(records) == 1
        assert records[0].collection_run_id == "run-2"
