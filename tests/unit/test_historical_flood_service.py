from types import SimpleNamespace

import geopandas as gpd
from shapely.geometry import box

from backend.app.services.historical_flood_service import analyze_complex, historical_exposure_index


def test_historical_buffers_and_years_use_metric_crs():
    traces = gpd.GeoDataFrame(
        {"source_year":[2022, 2024]},
        geometry=[box(953850, 1951750, 953950, 1951850), box(954200, 1951750, 954250, 1951800)],
        crs="EPSG:5179",
    )
    point = gpd.GeoSeries.from_xy([953900], [1951800], crs="EPSG:5179").to_crs("EPSG:4326").iloc[0]
    result = analyze_complex(traces, point.x, point.y)
    assert result["intersects_trace"] is True
    assert result["hit_years_point"] == [2022]
    assert result["hit_years_500m"] == [2022, 2024]
    assert result["overlap_ratio_100m"] > 0


def test_historical_index_is_explicit_proximity_not_probability():
    feature = SimpleNamespace(
        intersects_trace=False,
        nearest_trace_distance_m=80,
        hit_years_100m=[2022, 2024],
    )
    assert historical_exposure_index(feature) == 80
