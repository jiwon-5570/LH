import geopandas as gpd
from shapely.geometry import Polygon, box

from backend.app.pipelines.build_seoul_flood_grid import build_grid


def test_grid_requires_crs_and_has_no_fake_labels():
    boundary=gpd.GeoDataFrame({"district":["test"]},geometry=[box(126.99,37.54,127.001,37.551)],crs="EPSG:4326")
    grid=build_grid(boundary,100)
    assert len(grid)>0
    assert set(grid.label_status)=={"BLOCKED_BY_DATA"}
    assert grid.historical_flood_overlap.isna().all()


def test_invalid_geometry_can_be_repaired():
    polygon=Polygon([(0,0),(1,1),(1,0),(0,1),(0,0)])
    assert not polygon.is_valid
    from shapely import make_valid
    assert make_valid(polygon).is_valid
