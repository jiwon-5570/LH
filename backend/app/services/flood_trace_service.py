from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
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


def _source_year(path: Path) -> int | None:
    match = re.search(r"(?:19|20)\d{2}", path.name)
    return int(match.group()) if match else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_flood_trace(source: Path, raw_dir: Path, staging_dir: Path, processed_dir: Path, quarantine_dir: Path) -> dict:
    for directory in (raw_dir, staging_dir, processed_dir, quarantine_dir):
        directory.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / source.name
    if source.resolve() != raw_path.resolve():
        shutil.copy2(source, raw_path)
    readable = _extract_source(raw_path, staging_dir)
    if readable.suffix.lower() == ".shp" and not readable.with_suffix(".cpg").exists():
        frame = gpd.read_file(readable, encoding="cp949")
    else:
        frame = gpd.read_file(readable)
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
    valid["source_year"] = _source_year(source)
    valid["source_file"] = source.name
    valid["data_version"] = _sha256(raw_path)
    valid["processed_at"] = datetime.now(UTC).isoformat()
    seoul_bbox = gpd.GeoSeries([box(126.734,37.413,127.270,37.715)],crs="EPSG:4326").to_crs(valid.crs).iloc[0]
    valid = valid[valid.geometry.intersects(seoul_bbox)].copy()
    processed_path = processed_dir / f"mois_flood_trace_{uuid.uuid4().hex[:8]}.parquet"
    valid.to_parquet(processed_path,index=False)
    if not quarantine.empty:
        quarantine.to_parquet(quarantine_dir / f"{processed_path.stem}_invalid.parquet",index=False)
    metadata = {"status":"COMPLETE","source_year":_source_year(source),"source_file":source.name,"data_version":_sha256(raw_path),"source_crs":original_crs,"source_features":len(frame),"invalid_before":int(invalid_before.sum()),"repaired":int((invalid_before & ~invalid_after).sum()),"quarantined":int(invalid_after.sum()),"seoul_features":len(valid),"seoul_filter_method":"coarse_bbox_v1","admin_boundary_status":"BLOCKED_BY_DATA","processed_path":str(processed_path),"processed_at":datetime.now(UTC).isoformat()}
    processed_path.with_suffix(".metadata.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
    return metadata


def consolidate_flood_traces(source_paths: list[Path], output_dir: Path) -> dict:
    """Create the canonical, deduplicated Seoul flood-trace GeoParquet."""
    frames = [gpd.read_parquet(path).to_crs("EPSG:5179") for path in source_paths]
    if not frames:
        raise FileNotFoundError("No processed flood-trace GeoParquet was found")
    frame = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs="EPSG:5179")
    polygon_mask = frame.geom_type.isin(["Polygon", "MultiPolygon"])
    frame = frame.loc[polygon_mask & frame.geometry.notna() & ~frame.geometry.is_empty].copy()
    event_date = pd.to_datetime(frame.get("F_SAT_YMD"), format="%Y%m%d", errors="coerce")
    event_year = pd.to_numeric(frame.get("F_YR"), errors="coerce").fillna(frame.get("source_year"))
    flood_depth = pd.to_numeric(frame.get("F_SHIM"), errors="coerce")
    district = frame.get("GU_NAM", pd.Series(pd.NA, index=frame.index, dtype="string"))
    identity = (
        event_year.astype("Int64").astype(str)
        + "|" + frame.geometry.map(lambda geometry: hashlib.sha256(geometry.wkb).hexdigest())
        + "|" + frame.get("PNU", pd.Series("", index=frame.index)).fillna("").astype(str)
    )
    duplicate_mask = identity.duplicated(keep="first")
    canonical = gpd.GeoDataFrame({
        "flood_trace_id": identity.map(lambda value: hashlib.sha256(value.encode()).hexdigest()[:24]),
        "event_year": event_year.astype("Int64"),
        "event_date": event_date,
        "flood_depth": flood_depth,
        "district": district,
        "geometry": frame.geometry,
        "source_name": "서울특별시 침수흔적도",
        "source_file": frame["source_file"],
        "data_version": frame["data_version"],
        "processed_at": datetime.now(UTC),
        "validation_status": "VALID",
        "geometry_repaired": frame.get("geometry_repaired", False),
    }, geometry="geometry", crs="EPSG:5179").loc[~duplicate_mask].copy()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "seoul_flood_trace.parquet"
    canonical.to_parquet(output_path, index=False)
    metadata = {
        "status": "COMPLETE", "input_features": len(frame),
        "output_features": len(canonical), "duplicate_features": int(duplicate_mask.sum()),
        "source_years": sorted(int(value) for value in canonical["event_year"].dropna().unique()),
        "crs": "EPSG:5179", "geometry_types": sorted(canonical.geom_type.unique().tolist()),
        "output_path": str(output_path), "processed_at": datetime.now(UTC).isoformat(),
    }
    output_path.with_suffix(".metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return metadata
