from __future__ import annotations

import json
import shutil
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
from shapely import make_valid
from shapely.geometry import box


def _extract_source(path: Path, staging_dir: Path) -> Path:
    if path.suffix.lower() != ".zip":
        return path
    target = staging_dir / f"{path.stem}_{uuid.uuid4().hex[:8]}"
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        archive.extractall(target)
    shapefiles = list(target.rglob("*.shp"))
    if len(shapefiles) != 1:
        raise ValueError(f"ZIP 내부 SHP는 정확히 1개여야 합니다: {len(shapefiles)}개")
    return shapefiles[0]


def process_flood_trace(source: Path, raw_dir: Path, staging_dir: Path, processed_dir: Path, quarantine_dir: Path) -> dict:
    for directory in (raw_dir, staging_dir, processed_dir, quarantine_dir):
        directory.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / source.name
    if source.resolve() != raw_path.resolve():
        shutil.copy2(source, raw_path)
    readable = _extract_source(raw_path, staging_dir)
    frame = gpd.read_file(readable, encoding="cp949" if readable.suffix.lower() == ".shp" else None)
    if frame.crs is None:
        metadata = {"status":"REVIEW_REQUIRED","reason":"CRS_MISSING","source":str(raw_path),"processed_at":datetime.now(UTC).isoformat()}
        (quarantine_dir / f"{raw_path.stem}_metadata.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
        return metadata
    original_crs = str(frame.crs)
    missing = frame.geometry.isna() | frame.geometry.is_empty
    invalid_before = ~frame.geometry.is_valid & ~missing
    frame.loc[invalid_before, "geometry"] = frame.loc[invalid_before, "geometry"].map(make_valid)
    invalid_after = ~frame.geometry.is_valid | frame.geometry.isna() | frame.geometry.is_empty
    quarantine = frame.loc[invalid_after].copy()
    valid = frame.loc[~invalid_after].copy()
    valid["geometry_repaired"] = invalid_before.loc[valid.index]
    valid["source_crs"] = original_crs
    valid["processed_at"] = datetime.now(UTC).isoformat()
    seoul_bbox = gpd.GeoSeries([box(126.734,37.413,127.270,37.715)],crs="EPSG:4326").to_crs(valid.crs).iloc[0]
    valid = valid[valid.geometry.intersects(seoul_bbox)].copy()
    processed_path = processed_dir / f"mois_flood_trace_{uuid.uuid4().hex[:8]}.parquet"
    valid.to_parquet(processed_path,index=False)
    if not quarantine.empty:
        quarantine.to_parquet(quarantine_dir / f"{processed_path.stem}_invalid.parquet",index=False)
    metadata = {"status":"COMPLETE","source_crs":original_crs,"source_features":len(frame),"invalid_before":int(invalid_before.sum()),"repaired":int((invalid_before & ~invalid_after).sum()),"quarantined":int(invalid_after.sum()),"seoul_features":len(valid),"seoul_filter_method":"coarse_bbox_v1","admin_boundary_status":"BLOCKED_BY_DATA","processed_path":str(processed_path),"processed_at":datetime.now(UTC).isoformat()}
    processed_path.with_suffix(".metadata.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
    return metadata
