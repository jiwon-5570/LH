"""Prepare a 100 m Seoul analysis grid schema; labels remain blocked without flood traces."""

from __future__ import annotations

import hashlib

import geopandas as gpd
import numpy as np
from shapely.geometry import box


def build_grid(boundary: gpd.GeoDataFrame, cell_size_m: int = 100) -> gpd.GeoDataFrame:
    if boundary.crs is None:
        raise ValueError("서울 경계 CRS가 필요합니다")
    metric = boundary.to_crs("EPSG:5179")
    minx, miny, maxx, maxy = metric.total_bounds
    cells = []
    for x in np.arange(np.floor(minx/cell_size_m)*cell_size_m, maxx, cell_size_m):
        for y in np.arange(np.floor(miny/cell_size_m)*cell_size_m, maxy, cell_size_m):
            geom = box(x,y,x+cell_size_m,y+cell_size_m)
            if metric.geometry.intersects(geom).any():
                cells.append({"grid_id":hashlib.sha1(f"{int(x)}:{int(y)}:{cell_size_m}".encode()).hexdigest()[:16],"geometry":geom,"elevation_mean":None,"elevation_min":None,"relative_elevation":None,"slope_mean":None,"lowland_index":None,"historical_flood_overlap":None,"historical_flood_area_ratio":None,"expected_flood_overlap":None,"expected_flood_stage":None,"district":None,"data_version":None,"label_status":"BLOCKED_BY_DATA"})
    return gpd.GeoDataFrame(cells,geometry="geometry",crs="EPSG:5179")
