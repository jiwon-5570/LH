from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

OFFICIAL_SOURCE_URL = "https://data.seoul.go.kr/dataList/OA-21179/A/1/datasetView.do"
OFFICIAL_SOURCE_CRS = "EPSG:5186"
OFFICIAL_SOURCE_ENCODING = "windows-949"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ingest_rain_pump(source: Path, root: Path) -> dict:
    version = _sha256(source)
    raw_dir = root / "data/raw/seoul_rain_pump"
    staging_dir = root / "data/staging/seoul_rain_pump" / version[:12]
    processed_dir = root / "data/processed/seoul_rain_pump"
    for directory in (raw_dir, staging_dir, processed_dir):
        directory.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / source.name
    if source.resolve() != raw_path.resolve():
        shutil.copy2(source, raw_path)
    with zipfile.ZipFile(raw_path) as archive:
        resolved_staging = staging_dir.resolve()
        for member in archive.infolist():
            target = (staging_dir / member.filename).resolve()
            if resolved_staging not in target.parents and target != resolved_staging:
                raise ValueError(f"ZIP 경로 이탈 항목: {member.filename}")
        archive.extractall(staging_dir)
    shapefiles = list(staging_dir.rglob("*.shp"))
    if len(shapefiles) != 1:
        raise ValueError(f"RAINPUMP ZIP에는 SHP가 정확히 1개여야 합니다: {len(shapefiles)}개")
    frame = gpd.read_file(shapefiles[0], encoding="cp949")
    if frame.crs is not None and frame.crs.to_epsg() != 5186:
        raise ValueError(f"공식 메타데이터와 다른 CRS: {frame.crs}")
    if frame.crs is None:
        frame = frame.set_crs(OFFICIAL_SOURCE_CRS)
    if not set(frame.geom_type).issubset({"Point", "MultiPoint"}):
        raise ValueError(f"예상하지 않은 도형 유형: {sorted(set(frame.geom_type))}")
    frame = frame.explode(index_parts=False, ignore_index=True).to_crs("EPSG:5179")
    frame = frame.rename(columns={"UNI_CD":"pump_id", "PUMP_NM":"pump_name", "OPR_YN":"operation_status", "EST_DT":"established_date"})
    frame["source_crs"] = OFFICIAL_SOURCE_CRS
    frame["crs_provenance"] = "official_metadata"
    frame["source_url"] = OFFICIAL_SOURCE_URL
    frame["source_file"] = source.name
    frame["data_version"] = version
    frame["processed_at"] = datetime.now(UTC).isoformat()
    processed_path = processed_dir / f"seoul_rain_pump_{version[:12]}.parquet"
    frame.to_parquet(processed_path, index=False)
    metadata = {
        "status":"COMPLETE", "records":len(frame), "source_crs":OFFICIAL_SOURCE_CRS,
        "crs_provenance":"official_metadata", "source_encoding":OFFICIAL_SOURCE_ENCODING,
        "source_url":OFFICIAL_SOURCE_URL, "data_version":version,
        "capacity_status":"NOT_PROVIDED", "operation_status":"NOT_PROVIDED",
        "processed_path":str(processed_path), "processed_at":datetime.now(UTC).isoformat(),
    }
    processed_path.with_suffix(".metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def analyze_complex(pumps: gpd.GeoDataFrame, longitude: float, latitude: float) -> dict:
    metric = pumps.to_crs("EPSG:5179")
    point = gpd.GeoSeries([Point(longitude, latitude)], crs="EPSG:4326").to_crs("EPSG:5179").iloc[0]
    distances = metric.geometry.distance(point)
    if distances.empty:
        return {
            "nearest_pump_id": None, "nearest_pump_name": None,
            "nearest_pump_distance_m": None, "pump_count_500m": 0,
            "pump_count_1km": 0, "pump_count_2km": 0,
            "pump_count_3km": 0, "pump_count_5km": 0,
        }
    nearest_index = distances.idxmin()
    nearest = metric.loc[nearest_index]
    return {
        "nearest_pump_id":None if pd.isna(nearest.get("pump_id")) else str(nearest.get("pump_id")),
        "nearest_pump_name":None if pd.isna(nearest.get("pump_name")) else str(nearest.get("pump_name")),
        "nearest_pump_distance_m":round(float(distances.loc[nearest_index]), 2),
        "pump_count_500m":int((distances <= 500).sum()),
        "pump_count_1km":int((distances <= 1000).sum()),
        "pump_count_2km":int((distances <= 2000).sum()),
        "pump_count_3km":int((distances <= 3000).sum()),
        "pump_count_5km":int((distances <= 5000).sum()),
    }
