from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from backend.app.services.terrain_service import TerrainAnalyzer, lowland_index


def write_dem(path: Path, data: np.ndarray, left: float, top: float, nodata: float = -9999) -> None:
    with rasterio.open(path,"w",driver="GTiff",height=data.shape[0],width=data.shape[1],count=1,dtype="float32",crs="EPSG:5179",transform=from_origin(left,top,10,10),nodata=nodata) as dst:
        dst.write(data.astype("float32"),1)


def test_lowland_definition():
    assert lowland_index(-10,5) == 100
    assert lowland_index(3,5) == 0
    assert lowland_index(None,5) is None


def test_dem_buffers_nodata_and_tile_boundary(tmp_path: Path):
    transformer = __import__("pyproj").Transformer.from_crs("EPSG:4326","EPSG:5179",always_xy=True)
    x,y=transformer.transform(127.0,37.55)
    first=np.full((120,60),20.0); second=np.full((120,60),30.0); first[0,0]=-9999
    p1=tmp_path/"a.tif"; p2=tmp_path/"b.tif"
    write_dem(p1,first,x-600,y+600); write_dem(p2,second,x,y+600)
    with TerrainAnalyzer([p1,p2]) as analyzer:
        result=analyzer.analyze("X",127.0,37.55)
    assert result["mean_elevation_100m"] is not None
    assert result["mean_elevation_300m"] is not None
    assert result["mean_elevation_500m"] is not None
    assert result["dem_coverage_ratio_300m"] > .8
    assert result["elevation_m"] != -9999
