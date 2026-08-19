"""Backfill Seoul LH complex coordinates from auditable official sources."""
from __future__ import annotations

import argparse
import math
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "lh_predict.db"
LINKAGE_PATH = ROOT / "data/processed/complex_linkage/complex_linkage.parquet"
ELEVATOR_COORD_DIR = ROOT / "data/processed/elevator_building_coordinates"
SEOUL_EXTENT = (37.413, 37.715, 126.734, 127.270)
MAX_ADDRESS_CLUSTER_METERS = 500.0


def _compact(value: object) -> str:
    text = str(value or "").replace("서울특별시", "서울").replace("서울시", "서울")
    return re.sub(r"[^0-9가-힣]", "", text)


def _address_keys(value: object) -> list[tuple[str, str]]:
    text = str(value or "").replace("서울특별시", "서울").replace("서울시", "서울")
    district = re.search(r"서울\s*([^\s,()]+구)", text)
    road = re.search(r"([^\s,()]+(?:대로|로|길))\s*(\d+(?:-\d+)?)", text)
    keys: list[tuple[str, str]] = []
    if district and road:
        keys.append(("road", f"{_compact(district.group(1))}:{_compact(road.group(1))}:{road.group(2)}"))
    lot = re.search(r"([^\s,()]+(?:동|가|리))\s*(?:산\s*)?(\d+(?:-\d+)?)", text)
    if district and lot:
        keys.append(("lot", f"{_compact(district.group(1))}:{_compact(lot.group(1))}:{lot.group(2)}"))
    return keys


def _address_key(value: object) -> tuple[str, str] | None:
    keys = _address_keys(value)
    return keys[0] if keys else None


def _in_korea(latitude: float, longitude: float) -> bool:
    return 33 <= latitude <= 39 and 124 <= longitude <= 132


def _in_seoul(latitude: float, longitude: float) -> bool:
    south, north, west, east = SEOUL_EXTENT
    return south <= latitude <= north and west <= longitude <= east


def _distance_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = math.radians(b_lat - a_lat), math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def _cluster_coordinate(rows: list[dict[str, object]]) -> tuple[float, float, float] | None:
    points = [(float(r["latitude"]), float(r["longitude"])) for r in rows
              if pd.notna(r.get("latitude")) and pd.notna(r.get("longitude"))]
    points = [(lat, lon) for lat, lon in points if _in_seoul(lat, lon)]
    if not points:
        return None
    latitude = float(pd.Series([p[0] for p in points]).median())
    longitude = float(pd.Series([p[1] for p in points]).median())
    spread = max(_distance_m(latitude, longitude, lat, lon) for lat, lon in points)
    return (latitude, longitude, spread) if spread <= MAX_ADDRESS_CLUSTER_METERS else None


def _latest_elevator_coordinates() -> Path | None:
    files = sorted(ELEVATOR_COORD_DIR.glob("*.parquet"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def _naver_geocode(address: str, env: dict[str, str | None]) -> tuple[float, float, str] | None:
    client_id = (env.get("NAVER_MAP_CLIENT_ID") or "").strip()
    secret = (env.get("NAVER_MAP_CLIENT_SECRET") or "").strip()
    if not client_id or not secret:
        return None
    url = (env.get("NAVER_GEOCODING_API_URL") or "https://maps.apigw.ntruss.com/map-geocode/v2/geocode").strip()
    response = httpx.get(url, params={"query": address}, headers={
        "x-ncp-apigw-api-key-id": client_id, "x-ncp-apigw-api-key": secret,
    }, timeout=15, trust_env=False)
    if response.status_code == 403:
        raise PermissionError("NAVER Geocoding API 권한이 활성화되지 않았습니다.")
    response.raise_for_status()
    rows = response.json().get("addresses") or []
    if len(rows) != 1:
        return None
    row = rows[0]
    latitude, longitude = float(row["y"]), float(row["x"])
    if not _in_seoul(latitude, longitude):
        return None
    return latitude, longitude, str(row.get("roadAddress") or row.get("jibunAddress") or address)


def _record(connection: sqlite3.Connection, complex_id: str, latitude: float, longitude: float,
            method: str, source: str, confidence: float) -> None:
    now = datetime.now(UTC).isoformat()
    connection.execute("""insert or replace into coordinate_corrections
        (complex_id,latitude,longitude,method,source_reference,confidence,corrected_at)
        values (?,?,?,?,?,?,?)""", (complex_id, latitude, longitude, method, source, confidence, now))
    connection.execute("update complexes set latitude=?,longitude=? where complex_id=?", (latitude, longitude, complex_id))
    connection.execute("update complex_data_links set latitude=?,longitude=? where complex_id=?", (latitude, longitude, complex_id))
    connection.execute("""update seoul_complex_profiles set latitude=?,longitude=?,validation_status='VALIDATED',
        eligibility_reason='공식 주소 기반 좌표 보정',updated_at=? where complex_id=?""", (latitude, longitude, now, complex_id))


def _source_index(frame: pd.DataFrame) -> dict[tuple[str, str], list[dict[str, object]]]:
    index: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in frame.to_dict("records"):
        for key in _address_keys(row.get("address")):
            index.setdefault(key, []).append(row)
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description="서울 LH 단지 좌표를 공식 주소 자료로 보정")
    parser.add_argument("--naver", action="store_true", help="공식 자료 미매칭 주소에 NAVER Geocoding 사용")
    args = parser.parse_args()
    connection = sqlite3.connect(DB_PATH)
    connection.execute("""create table if not exists coordinate_corrections (
        complex_id text primary key, latitude real not null, longitude real not null,
        method text not null, source_reference text not null, confidence real not null,
        corrected_at text not null)""")
    missing = pd.read_sql_query("""select complex_id,complex_name,address from seoul_complex_profiles
        where latitude is null or longitude is null""", connection)

    sources: list[tuple[str, Path, pd.DataFrame, float]] = []
    elevator_path = _latest_elevator_coordinates()
    if elevator_path:
        elevator = pd.read_parquet(elevator_path, columns=["address", "latitude", "longitude"])
        elevator = elevator[elevator["address"].astype(str).str.contains("서울", na=False)]
        sources.append(("official_elevator_address_cluster", elevator_path, elevator, 0.99))
    if LINKAGE_PATH.exists():
        linkage = pd.read_parquet(LINKAGE_PATH).dropna(subset=["latitude", "longitude"])
        sources.append(("verified_local_address", LINKAGE_PATH, linkage, 1.0))

    corrected: set[str] = set()
    rejected_clusters = 0
    for method, path, frame, confidence in sources:
        index = _source_index(frame)
        for row in missing.loc[~missing["complex_id"].isin(corrected)].to_dict("records"):
            profile_keys = _address_keys(row["address"])
            matched = next(((key, index[key]) for key in profile_keys if key in index), None)
            key, candidates = matched if matched else (None, [])
            coordinate = _cluster_coordinate(candidates)
            if not coordinate:
                rejected_clusters += int(bool(candidates))
                continue
            latitude, longitude, spread = coordinate
            source = f"{path.relative_to(ROOT)} | key={key[0]}:{key[1]} | records={len(candidates)} | max_spread_m={spread:.1f}"
            _record(connection, str(row["complex_id"]), latitude, longitude, method, source, confidence)
            corrected.add(str(row["complex_id"]))

    naver_corrected, naver_error = 0, None
    if args.naver:
        env = dotenv_values(ROOT / ".env")
        for row in missing.loc[~missing["complex_id"].isin(corrected)].to_dict("records"):
            try:
                result = _naver_geocode(str(row["address"]), env)
            except PermissionError as exc:
                naver_error = str(exc)
                break
            except (httpx.HTTPError, ValueError) as exc:
                naver_error = f"{type(exc).__name__}: {exc}"
                continue
            if result:
                latitude, longitude, matched_address = result
                _record(connection, str(row["complex_id"]), latitude, longitude, "naver_geocoding_unique", matched_address, 0.95)
                naver_corrected += 1
    connection.commit()
    remaining = connection.execute("select count(*) from seoul_complex_profiles where latitude is null or longitude is null").fetchone()[0]
    connection.close()
    print({"missing_before": len(missing), "official_or_local_corrected": len(corrected),
           "rejected_wide_clusters": rejected_clusters, "naver_corrected": naver_corrected,
           "remaining": remaining, "naver_status": naver_error or ("NOT_REQUESTED" if not args.naver else "COMPLETE"),
           "official_coordinate_file": str(elevator_path.relative_to(ROOT)) if elevator_path else None})


if __name__ == "__main__":
    main()
