import pandas as pd

from backend.app.collectors.pipeline import validate
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
