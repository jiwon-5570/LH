import pandas as pd

from backend.app.services.rainfall_history_service import (
    empirical_rain_index,
    normalize_station_name,
    rainfall_accumulation,
)


def test_empirical_rain_index_uses_observed_quantiles():
    reference = {"p50":1.0,"p90":5.0,"p95":10.0,"p99":20.0,"p99_9":40.0,"max":60.0}
    assert empirical_rain_index(0, reference) == 0
    assert empirical_rain_index(5, reference) == 90
    assert empirical_rain_index(20, reference) == 99
    assert empirical_rain_index(40, reference) == 100
    assert empirical_rain_index(100, reference) == 100
    assert empirical_rain_index(None, reference) is None


def test_station_name_normalization_is_exact_not_fuzzy():
    assert normalize_station_name("서울특별시 강남(본소)") == "강남"
    assert normalize_station_name("강남-1") != normalize_station_name("강남-2")


def test_rainfall_accumulation_requires_coverage_and_never_fills_zero():
    end = pd.Timestamp("2026-08-21T01:00:00Z")
    complete = pd.DataFrame({
        "observed_at": pd.date_range("2026-08-21T00:10:00Z", periods=6, freq="10min"),
        "rainfall_mm": [1.0, 2.0, 0.0, 3.0, 4.0, 5.0],
    })
    result = rainfall_accumulation(complete, end, 60)
    assert result["rainfall_mm"] == 15.0
    assert result["coverage_ratio"] == 1.0
    partial = rainfall_accumulation(complete.iloc[:2], end, 60)
    assert partial["rainfall_mm"] is None
    assert partial["quality_status"] == "INSUFFICIENT"
