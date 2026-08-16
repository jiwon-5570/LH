from backend.app.services.rainfall_history_service import empirical_rain_index


def test_empirical_rain_index_uses_observed_quantiles():
    reference = {"p50":1.0,"p90":5.0,"p95":10.0,"p99":20.0,"p99_9":40.0,"max":60.0}
    assert empirical_rain_index(0, reference) == 0
    assert empirical_rain_index(5, reference) == 90
    assert empirical_rain_index(20, reference) == 99
    assert empirical_rain_index(40, reference) == 100
    assert empirical_rain_index(100, reference) == 100
    assert empirical_rain_index(None, reference) is None
