from backend.app.collectors.registry import load_registry


def test_all_requested_datasets_are_registered():
    registry = load_registry()
    assert len(registry) == 21
    assert "lh_complexes" in registry
    assert "ngii_dem" in registry
    assert "elevator_corrective_actions" in registry
    assert registry["mois_flood_trace_api"].api_key_env == "MOIS_FLOOD_TRACE_API_KEY"
    assert registry["seoul_rain_pump_stations"].domain == "drainage_infrastructure"
    assert registry["seoul_rainfall_historical"].domain == "rainfall_history"
    assert registry["seoul_flood_trace"].domain == "flood_history_geometry"
    assert registry["seoul_flood_forecast_geometry"].domain == "flood_forecast_area"
    assert registry["seoul_rain_gauge_locations"].domain == "rain_gauge_location"
    assert registry["seoul_pump_station_attributes"].domain == "pump_station_attribute"
    assert registry["seoul_river_levels"].domain == "river_level"

def test_every_dataset_has_input_contract():
    for spec in load_registry().values():
        assert spec.name and spec.mode in {"file", "api", "file_or_api"}
        assert spec.formats
