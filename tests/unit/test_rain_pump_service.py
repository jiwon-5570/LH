import geopandas as gpd
from shapely.geometry import Point

from backend.app.services.rain_pump_service import analyze_complex


def test_rain_pump_proximity_uses_metric_distance():
    pumps = gpd.GeoDataFrame(
        {"pump_id":["A", "B"], "pump_name":["가", "나"]},
        geometry=[Point(953900, 1951800), Point(956000, 1951800)],
        crs="EPSG:5179",
    )
    complex_point = gpd.GeoSeries([Point(954000, 1951800)], crs="EPSG:5179").to_crs("EPSG:4326").iloc[0]
    result = analyze_complex(pumps, complex_point.x, complex_point.y)
    assert result["nearest_pump_id"] == "A"
    assert 99 <= result["nearest_pump_distance_m"] <= 101
    assert result["pump_count_500m"] == 1
    assert result["pump_count_1km"] == 1
    assert result["pump_count_2km"] == 2
    assert result["pump_count_3km"] == 2
