from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import uuid
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pandas as pd
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.app.collectors.registry import DatasetSpec, get_dataset
from backend.app.core.config import get_settings
from backend.app.db.base import Base, Complex, DataCollectionRun, DataQualityResult, SourceRecord
from backend.app.db.session import SessionLocal, engine

load_dotenv()

def _utcnow() -> datetime:
    return datetime.now(UTC)

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _normalize_name(value: str) -> str:
    return "".join(str(value).strip().lower().replace("_", "").split())

def _rename_aliases(frame: pd.DataFrame, spec: DatasetSpec) -> pd.DataFrame:
    normalized = {_normalize_name(column): column for column in frame.columns}
    result = frame.copy()
    for canonical, aliases in spec.aliases.items():
        candidates: list[str] = []
        for alias in aliases:
            original = normalized.get(_normalize_name(alias))
            if original is not None and original not in candidates:
                candidates.append(original)
        if not candidates:
            continue
        if canonical not in result.columns:
            result = result.rename(columns={candidates.pop(0): canonical})
        # Official APIs sometimes return a blank preferred field plus a populated
        # legacy alias. Coalesce exact aliases without discarding provenance cols.
        for candidate in candidates:
            if candidate == canonical or candidate not in result.columns:
                continue
            missing = result[canonical].isna() | result[canonical].astype(str).str.strip().eq("")
            result.loc[missing, canonical] = result.loc[missing, candidate]
    return result


def _spatialize(frame: pd.DataFrame, spec: DatasetSpec) -> pd.DataFrame:
    """Create verified Geometry without inventing coordinates or CRS."""
    has_coordinates = {"latitude", "longitude"}.issubset(frame.columns)
    if "geometry" not in spec.required and "geometry" not in frame.columns and not has_coordinates:
        return frame
    import geopandas as gpd
    from shapely import wkt
    from shapely.geometry import shape

    if "geometry" not in frame.columns and has_coordinates:
        latitude = pd.to_numeric(frame["latitude"], errors="coerce")
        longitude = pd.to_numeric(frame["longitude"], errors="coerce")
        return gpd.GeoDataFrame(
            frame, geometry=gpd.points_from_xy(longitude, latitude), crs="EPSG:4326"
        )
    if "geometry" not in frame.columns:
        return frame

    def parse(value):
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if hasattr(value, "geom_type"):
            return value
        if isinstance(value, dict):
            return shape(value)
        text = str(value).strip()
        if text.startswith("{"):
            return shape(json.loads(text))
        return wkt.loads(text)

    parsed = frame["geometry"].map(parse)
    source_crs = os.getenv(f"{spec.id.upper()}_SOURCE_CRS", "").strip()
    if not source_crs:
        raise ValueError(
            f"{spec.id} Geometry CRS is unknown; set {spec.id.upper()}_SOURCE_CRS"
        )
    return gpd.GeoDataFrame(frame.drop(columns=["geometry"]), geometry=parsed, crs=source_crs)

def _read_json_records(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return payload
    candidates = [payload]
    while candidates:
        current = candidates.pop(0)
        if isinstance(current, list) and (not current or isinstance(current[0], dict)):
            return current
        if isinstance(current, dict):
            nested = False
            for key in ("items", "item", "row", "rows", "data", "body", "response"):
                if key in current:
                    candidates.append(current[key])
                    nested = True
            if not nested:
                for value in current.values():
                    if isinstance(value, (dict, list)):
                        candidates.append(value)
                        nested = True
            if not nested and current and all(not isinstance(value, (dict, list)) for value in current.values()):
                return [current]
    raise ValueError("API 응답에서 레코드 배열을 찾지 못했습니다")

def _read_xml_records(content: bytes) -> list[dict]:
    root = ET.fromstring(content)
    items = root.findall(".//item") or root.findall(".//row")
    return [{child.tag.split("}")[-1]: child.text for child in item} for item in items]

def _response_total_count(payload: Any) -> int | None:
    """Find a pagination total without depending on one gateway envelope."""
    queue = [payload]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            for key in ("totalCount", "total_count", "list_total_count"):
                if key in current:
                    try:
                        return int(current[key])
                    except (TypeError, ValueError):
                        return None
            queue.extend(value for value in current.values() if isinstance(value, (dict, list)))
        elif isinstance(current, list):
            queue.extend(value for value in current if isinstance(value, (dict, list)))
    return None

def _raise_gateway_error(payload: Any) -> None:
    """Surface Safety Data/Data.go.kr authentication errors before validation."""
    text = json.dumps(payload, ensure_ascii=False)
    error_markers = (
        "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
        "SERVICE_ACCESS_DENIED_ERROR",
        "DEADLINE_HAS_EXPIRED_ERROR",
        "UNREGISTERED_IP_ERROR",
        "NO_SERVICE_KEY_ERROR",
    )
    marker = next((item for item in error_markers if item in text), None)
    if marker:
        raise RuntimeError(f"재난안전데이터 API 인증 실패: {marker}")

def read_file(path: Path, spec: DatasetSpec):
    suffix = path.suffix.lower().lstrip(".")
    if suffix not in spec.formats:
        raise ValueError(f"{spec.id} 허용 형식: {', '.join(spec.formats)}")
    if suffix == "csv":
        for encoding in ("utf-8-sig", "cp949", "euc-kr"):
            try: return pd.read_csv(path, encoding=encoding, dtype="string")
            except UnicodeDecodeError: continue
        raise ValueError("CSV 인코딩을 판별할 수 없습니다")
    if suffix in {"xlsx", "xls"}:
        # The official Seoul rain-gauge workbook has a blank title row and its
        # actual column names on the second row.
        header = 1 if spec.id == "seoul_rain_gauge_locations" else 0
        return pd.read_excel(path, header=header, dtype="string")
    if suffix == "json": return pd.DataFrame(_read_json_records(json.loads(path.read_text(encoding="utf-8-sig"))))
    if suffix == "zip" and spec.domain == "terrain":
        extract_dir = path.parent / f"{path.stem}_extracted"
        with zipfile.ZipFile(path) as archive:
            archive.extractall(extract_dir)
        rasters = [item for item in extract_dir.rglob("*") if item.suffix.lower() in {".tif", ".tiff", ".img"}]
        if len(rasters) != 1: raise ValueError(f"DEM ZIP에는 래스터 파일이 정확히 1개 있어야 합니다: {len(rasters)}개 발견")
        return read_file(rasters[0], spec)
    if suffix in {"geojson", "gpkg", "shp", "zip"}:
        import geopandas as gpd
        return gpd.read_file(path)
    if suffix in {"tif", "tiff", "img"}:
        import rasterio
        dataset = rasterio.open(path)
        if dataset.crs is None: raise ValueError("DEM 좌표계(CRS)가 없습니다")
        return dataset
    raise ValueError(f"지원하지 않는 형식: {suffix}")

@retry(stop=stop_after_attempt(4), wait=wait_exponential(min=1, max=10), reraise=True)
def _get_page(url: str, params: dict[str, Any]) -> httpx.Response:
    response = httpx.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response

def _latest_forecast_base(now: datetime | None = None) -> tuple[str, str]:
    current = now or datetime.now(ZoneInfo("Asia/Seoul"))
    candidates = (2, 5, 8, 11, 14, 17, 20, 23)
    available = [hour for hour in candidates if current.hour > hour or (current.hour == hour and current.minute >= 10)]
    if available:
        return current.strftime("%Y%m%d"), f"{available[-1]:02d}00"
    previous = current - timedelta(days=1)
    return previous.strftime("%Y%m%d"), "2300"

def _sample_kapt_code(key: str) -> str:
    list_url = os.getenv("MOLIT_COMPLEX_LIST_API_URL", "")
    if not list_url: raise RuntimeError("MOLIT_COMPLEX_LIST_API_URL 미설정")
    response = _get_page(list_url, {"ServiceKey":key,"pageNo":1,"numOfRows":1,"_type":"json"})
    records = _read_json_records(response.json())
    if not records or not records[0].get("kaptCode"): raise RuntimeError("공동주택 단지코드를 확보하지 못했습니다")
    return str(records[0]["kaptCode"])

def _lh_kapt_codes(limit: int) -> list[str]:
    processed = list((get_settings().processed_data_dir / "molit_complex_list").glob("*.parquet"))
    if not processed: return []
    frame = pd.read_parquet(max(processed, key=lambda path: path.stat().st_mtime), columns=["kapt_code", "complex_name"])
    with SessionLocal() as db:
        lh_names = [name for (name,) in db.query(Complex.complex_name).all()]
    wanted = {_normalize_name(name) for name in lh_names}
    codes = frame.loc[frame["complex_name"].map(_normalize_name).isin(wanted), "kapt_code"].dropna().astype(str).drop_duplicates().tolist()
    return codes[:limit]

def _fetch_kapt_details(spec: DatasetSpec, url: str, key: str, max_items: int) -> tuple[pd.DataFrame, bytes]:
    codes = _lh_kapt_codes(max_items) or [_sample_kapt_code(key)]
    search_month = (datetime.now(UTC)-timedelta(days=35)).strftime("%Y%m")
    def fetch_one(index_code: tuple[int, str]) -> tuple[int, list[dict], str]:
        index, code = index_code
        params: dict[str, Any] = {"ServiceKey":key,"_type":"json","kaptCode":code}
        if spec.id == "kapt_maintenance_cost": params["searchDate"] = search_month
        response = _get_page(url, params)
        payload = response.json()
        body = payload.get("response", {}).get("body", {})
        items = body.get("items", body.get("item", [])) if isinstance(body, dict) else []
        if isinstance(items, list): records = items
        elif isinstance(items, dict) and "item" in items: records = items["item"] if isinstance(items["item"], list) else [items["item"]]
        elif isinstance(items, dict) and items: records = [items]
        else: records = []
        for record in records:
            if not record.get("kaptCode"): record["kaptCode"] = code
            if spec.id == "kapt_maintenance_cost": record.setdefault("searchDate", search_month)
        return index, records, response.text
    pages: dict[int, tuple[list[dict], str]] = {}
    workers = min(int(os.getenv("DATA_GO_KR_MAX_WORKERS", "8")), len(codes))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch_one, pair) for pair in enumerate(codes, start=1)]
        for future in as_completed(futures):
            index, records, text = future.result(); pages[index] = (records, text)
    all_records: list[dict] = []; raw_pages: list[dict] = []
    for index in sorted(pages):
        records, text = pages[index]; all_records.extend(records); raw_pages.append({"request":index,"body":text})
    return pd.DataFrame(all_records), json.dumps(raw_pages, ensure_ascii=False).encode("utf-8")

def fetch_api(spec: DatasetSpec, max_pages: int = 100) -> tuple[pd.DataFrame, bytes]:
    url = os.getenv(spec.api_url_env or "", "")
    key = os.getenv(spec.api_key_env or "", "")
    if not url: raise RuntimeError(f"{spec.api_url_env} 미설정")
    if spec.api_key_env and not key: raise RuntimeError(f"{spec.api_key_env} 미설정")
    if spec.id in {"molit_complex_basic", "kapt_maintenance_cost"}:
        return _fetch_kapt_details(spec, url, key, max_pages)
    if spec.id == "mois_flood_trace_api":
        page_size = 1000
        all_records: list[dict] = []
        raw_pages: list[dict] = []
        total_count: int | None = None
        for page in range(1, max_pages + 1):
            response = _get_page(url, {
                "serviceKey":key,
                "pageNo":page,
                "numOfRows":page_size,
                "returnType":"json",
            })
            if response.content.lstrip().startswith(b"<"):
                records = _read_xml_records(response.content)
                payload: Any = response.text
            else:
                payload = response.json()
                _raise_gateway_error(payload)
                records = _read_json_records(payload)
                total_count = total_count if total_count is not None else _response_total_count(payload)
            raw_pages.append({"page":page,"body":response.text})
            all_records.extend(records)
            if not records or len(records) < page_size or (total_count is not None and len(all_records) >= total_count):
                break
        return pd.DataFrame(all_records), json.dumps(raw_pages, ensure_ascii=False).encode("utf-8")
    if "api.odcloud.kr" in url:
        def fetch_odcloud_page(page_number: int) -> tuple[int, dict, str]:
            response = _get_page(url, {"page":page_number,"perPage":1000,"serviceKey":key,"returnType":"JSON"})
            payload = response.json()
            return page_number, payload, response.text

        first_page, first_payload, first_text = fetch_odcloud_page(1)
        total_count = int(first_payload.get("totalCount", len(first_payload.get("data", []))))
        total_pages = min(max_pages, max(1, math.ceil(total_count / 1000)))
        pages: dict[int, tuple[dict, str]] = {first_page:(first_payload, first_text)}
        workers = min(int(os.getenv("ODCLOUD_MAX_WORKERS", "8")), total_pages)
        if total_pages > 1:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(fetch_odcloud_page, page) for page in range(2, total_pages + 1)]
                for future in as_completed(futures):
                    page_number, payload, text = future.result()
                    pages[page_number] = (payload, text)
        all_records: list[dict] = []
        raw_pages: list[dict] = []
        for page_number in sorted(pages):
            payload, text = pages[page_number]
            all_records.extend(_read_json_records(payload))
            raw_pages.append({"page":page_number,"body":text})
        return pd.DataFrame(all_records), json.dumps(raw_pages, ensure_ascii=False).encode("utf-8")
    all_records: list[dict] = []; raw_pages: list[dict] = []
    for page in range(1, max_pages + 1):
        if "openapi.seoul.go.kr" in url:
            start = (page - 1) * 1000 + 1; end = page * 1000
            values = {"key": key, "start": start, "end": end}
            if spec.id == "seoul_sewer_level":
                now_seoul = datetime.now(ZoneInfo("Asia/Seoul")).replace(minute=0, second=0, microsecond=0)
                configured_start = os.getenv("SEOUL_SEWER_START_TIME", "auto-6h")
                configured_end = os.getenv("SEOUL_SEWER_END_TIME", "auto")
                start_time = (now_seoul - timedelta(hours=6)).strftime("%Y%m%d%H") if configured_start == "auto-6h" else configured_start
                end_time = now_seoul.strftime("%Y%m%d%H") if configured_end == "auto" else configured_end
                values.update({"district_code":os.getenv("SEOUL_SEWER_DISTRICT_CODE","01"),"start_time":start_time,"end_time":end_time})
                if not values["start_time"] or not values["end_time"]: raise RuntimeError("SEOUL_SEWER_START_TIME/SEOUL_SEWER_END_TIME 미설정 (YYYYMMDDHH)")
            request_url = url.format(**values); params = {}
        elif "api.odcloud.kr" in url:
            request_url = url; params = {"page":page,"perPage":1000,"serviceKey":key,"returnType":"JSON"}
        else:
            page_size = 999 if spec.id == "kma_asos_hourly" else 1000
            request_url = url; params = {"pageNo":page,"numOfRows":page_size,"dataType":"JSON"}
            if key: params["ServiceKey"] = key
            if spec.id == "molit_complex_list": params["_type"] = "json"
            elif spec.id == "molit_complex_basic":
                params.update({"_type":"json","kaptCode":os.getenv("MOLIT_SAMPLE_KAPT_CODE") or _sample_kapt_code(key)})
            elif spec.id == "kapt_maintenance_cost":
                params.update({"_type":"json","kaptCode":os.getenv("MOLIT_SAMPLE_KAPT_CODE") or _sample_kapt_code(key),"searchDate":(datetime.now(UTC)-timedelta(days=35)).strftime("%Y%m")})
            elif spec.id == "kma_vilage_forecast":
                base_date, base_time = _latest_forecast_base()
                params.update({"base_date":base_date,"base_time":base_time,"nx":os.getenv("KMA_FORECAST_NX","60"),"ny":os.getenv("KMA_FORECAST_NY","127")})
            elif spec.id == "kma_asos_hourly":
                day = (datetime.now(ZoneInfo("Asia/Seoul"))-timedelta(days=1)).strftime("%Y%m%d")
                params.update({"dataCd":"ASOS","dateCd":"HR","startDt":day,"startHh":"00","endDt":day,"endHh":"23","stnIds":os.getenv("KMA_ASOS_STATION_IDS","108")})
        response = _get_page(request_url, params)
        content_type = response.headers.get("content-type", "")
        records = _read_xml_records(response.content) if "xml" in content_type or response.content.lstrip().startswith(b"<") else _read_json_records(response.json())
        if spec.id == "kapt_maintenance_cost":
            for record in records:
                if not record.get("kaptCode"): record["kaptCode"] = params["kaptCode"]
                record.setdefault("searchDate", params["searchDate"])
        raw_pages.append({"page": page, "body": response.text})
        all_records.extend(records)
        expected_page_size = int(params.get("perPage", params.get("numOfRows", 1000))) if params else 1000
        if len(records) < expected_page_size: break
    return pd.DataFrame(all_records), json.dumps(raw_pages, ensure_ascii=False).encode("utf-8")

def validate(frame: pd.DataFrame, spec: DatasetSpec) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    frame = _rename_aliases(frame, spec).copy()
    if spec.id == "seoul_rain_gauge_locations" and {"station_id", "started_at"}.issubset(frame.columns):
        # The source contains every relocation history. Operational proximity
        # features need exactly the latest known location for each station.
        frame = frame.dropna(how="all")
        frame["started_at"] = pd.to_datetime(frame["started_at"], errors="coerce")
        if "ended_at" in frame:
            frame["ended_at"] = pd.to_datetime(frame["ended_at"], errors="coerce")
        frame = (
            frame.sort_values(["station_id", "started_at"], na_position="first")
            .drop_duplicates("station_id", keep="last")
            .reset_index(drop=True)
        )
    frame = _spatialize(frame, spec)
    checks: list[dict] = []
    missing = [column for column in spec.required if column not in frame.columns]
    if missing: raise ValueError(f"필수 표준 컬럼 누락: {missing}; 실제 컬럼: {list(frame.columns)}")
    invalid = pd.Series(False, index=frame.index)
    for column in spec.required:
        failed = frame[column].isna() | frame[column].astype(str).str.strip().eq("")
        invalid |= failed
        checks.append({"check_name": f"required:{column}", "status": "fail" if failed.any() else "pass", "failed_count": int(failed.sum()), "details": {}})
    if "latitude" in frame and "longitude" in frame:
        lat = pd.to_numeric(frame["latitude"], errors="coerce"); lon = pd.to_numeric(frame["longitude"], errors="coerce")
        failed = ~(lat.between(33, 39) & lon.between(124, 132)); invalid |= failed
        frame["latitude"] = lat; frame["longitude"] = lon
        checks.append({"check_name":"coordinate_range","status":"fail" if failed.any() else "pass","failed_count":int(failed.sum()),"details":{"latitude":"33..39","longitude":"124..132"}})
    unique_identities = {
        "lh_complexes": ("complex_id",),
        "molit_complex_list": ("kapt_code",),
        "elevator_installations": ("elevator_id",),
        "seoul_rain_gauge_locations": ("station_id",),
    }.get(spec.id, ())
    for identity in unique_identities:
        if identity in frame:
            failed = frame[identity].notna() & frame[identity].duplicated(keep=False); invalid |= failed
            checks.append({"check_name":f"unique:{identity}","status":"fail" if failed.any() else "pass","failed_count":int(failed.sum()),"details":{}})
    frame["validation_status"] = "valid"
    quarantine = frame.loc[invalid].copy(); quarantine["validation_status"] = "invalid"
    return frame.loc[~invalid].copy(), quarantine, checks

def _record_payload(row: dict) -> dict:
    payload = {}
    for key, value in row.items():
        if key == "geometry" and value is not None:
            payload[key] = value.wkt
        elif pd.isna(value):
            payload[key] = None
        elif isinstance(value, (datetime, pd.Timestamp)):
            payload[key] = value.isoformat()
        elif hasattr(value, "item"):
            payload[key] = value.item()
        else:
            payload[key] = value
    return payload

def _persist_valid_records(db, valid: pd.DataFrame, spec: DatasetSpec, run_id: str, version: str, collected_at: datetime) -> None:
    # The complete validated frame is already stored as compressed Parquet.
    # SQLite keeps only a small recent sample for fast API previews.
    sample_limit = max(0, get_settings().source_record_sample_limit)
    if sample_limit == 0:
        return
    valid = valid.tail(sample_limit)
    identity_columns = [column for column in ("complex_id", "kapt_code", "elevator_id", "inspection_history_code", "sensor_id", "station_id", "address") if column in valid.columns]
    for ordinal, row in enumerate(valid.to_dict(orient="records")):
        natural_id = "|".join(str(row[column]) for column in identity_columns) if identity_columns else "row"
        source_id = f"{natural_id}|{ordinal}"
        key = hashlib.sha256(f"{spec.id}|{source_id}|{version}".encode()).hexdigest()
        # A source snapshot may be collected repeatedly with the same content hash.
        # Merge the bounded preview sample so reruns refresh metadata instead of
        # failing the whole collection on the primary-key constraint.
        db.merge(SourceRecord(
            source_record_key=key,
            dataset_id=spec.id,
            source_record_id=source_id,
            collection_run_id=run_id,
            payload=_record_payload(row),
            data_version=version,
            validation_status="valid",
            collected_at=collected_at,
        ))
    if spec.id == "lh_complexes":
        for row in valid.to_dict(orient="records"):
            db.merge(Complex(complex_id=str(row["complex_id"]),complex_name=str(row["complex_name"]),address=str(row["address"]),latitude=None if pd.isna(row.get("latitude")) else float(row["latitude"]),longitude=None if pd.isna(row.get("longitude")) else float(row["longitude"]),source_name=spec.name,source_url=None,collected_at=collected_at,observed_at=None,data_version=version,validation_status="valid",collection_run_id=run_id))

def ingest(dataset_id: str, input_path: Path | None = None, max_pages: int = 100) -> dict:
    spec = get_dataset(dataset_id); settings = get_settings(); started = _utcnow()
    run_id = f"{dataset_id}-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    raw_dir = settings.raw_data_dir / dataset_id / run_id; staging_dir = settings.staging_data_dir / dataset_id
    processed_dir = settings.processed_data_dir / dataset_id; quarantine_dir = settings.quarantine_data_dir / dataset_id
    for directory in (raw_dir, staging_dir, processed_dir, quarantine_dir): directory.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    run = DataCollectionRun(collection_run_id=run_id,dataset_id=dataset_id,source_name=spec.name,started_at=started,status="running")
    with SessionLocal() as db: db.add(run); db.commit()
    try:
        if input_path:
            source = input_path.resolve(); raw_path = raw_dir / source.name; shutil.copy2(source, raw_path); frame = read_file(raw_path, spec)
        else:
            frame, raw_bytes = fetch_api(spec, max_pages=max_pages); raw_path = raw_dir / "response_pages.json"; raw_path.write_bytes(raw_bytes)
        if not isinstance(frame, pd.DataFrame):
            metadata = {"driver": frame.driver, "crs": str(frame.crs), "bounds": list(frame.bounds), "width": frame.width, "height": frame.height, "nodata": frame.nodata, "count": frame.count}
            metadata["source_file"] = raw_path.name
            metadata["resolution"] = list(frame.res)
            processed_path = processed_dir / f"{run_id}_raster_metadata.json"
            processed_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            valid_count = 1; quarantined_count = 0; record_count = 1; checks = []
            frame.close()
        else:
            valid, quarantine, checks = validate(frame, spec); record_count = len(frame); valid_count = len(valid); quarantined_count = len(quarantine)
            collected_datetime = _utcnow(); collected_at = collected_datetime.isoformat(); version = _sha256(raw_path)
            for output in (valid, quarantine):
                output["source_name"] = spec.name; output["source_record_id"] = output.index.astype(str); output["collected_at"] = collected_at
                output["processed_at"] = collected_at; output["data_version"] = version; output["collection_run_id"] = run_id
            processed_path = processed_dir / f"{run_id}.parquet"; valid.to_parquet(processed_path, index=False)
            if not quarantine.empty: quarantine.to_parquet(quarantine_dir / f"{run_id}.parquet", index=False)
        with SessionLocal() as db:
            stored = db.get(DataCollectionRun, run_id); stored.finished_at = _utcnow(); stored.status = "success"; stored.raw_path = str(raw_path)
            stored.processed_path = str(processed_path); stored.record_count = record_count; stored.valid_count = valid_count; stored.quarantined_count = quarantined_count; stored.data_version = _sha256(raw_path)
            for index, check in enumerate(checks): db.add(DataQualityResult(quality_result_id=f"{run_id}-{index}",collection_run_id=run_id,dataset_id=dataset_id,created_at=_utcnow(),**check))
            if isinstance(frame, pd.DataFrame): _persist_valid_records(db, valid, spec, run_id, stored.data_version, collected_datetime)
            db.commit()
        return {"collection_run_id":run_id,"dataset_id":dataset_id,"records":record_count,"valid":valid_count,"quarantined":quarantined_count,"processed_path":str(processed_path)}
    except Exception as exc:
        with SessionLocal() as db:
            stored = db.get(DataCollectionRun, run_id); stored.finished_at = _utcnow(); stored.status = "failed"; stored.failure_reason = str(exc); db.commit()
        raise
