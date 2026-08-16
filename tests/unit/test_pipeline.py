import json

import pandas as pd

from backend.app.collectors.pipeline import _raise_gateway_error, validate
from backend.app.collectors.registry import get_dataset


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
