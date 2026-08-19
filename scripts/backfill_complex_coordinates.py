"""Backfill complex coordinates with auditable, high-confidence address matches.

Only unique road-name/building-number or legal-dong/lot-number matches are
applied automatically. Optional NAVER geocoding is intentionally opt-in.
"""

from __future__ import annotations

import argparse
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
SEOUL_EXTENT = (37.413, 37.715, 126.734, 127.270)


def _compact(value: object) -> str:
    text = str(value or "").replace("서울특별시", "서울").replace("경기도", "경기")
    return re.sub(r"[^0-9가-힣]", "", text)


def _address_key(value: object) -> tuple[str, str] | None:
    text = str(value or "")
    road = re.search(r"([가-힣0-9]+(?:로|길))\s*(\d+(?:-\d+)?)", text)
    if road:
        return "road", f"{_compact(road.group(1))}:{road.group(2)}"
    lot = re.search(r"([가-힣0-9]+(?:동|리))\s*(\d+(?:-\d+)?)", text)
    if lot:
        return "lot", f"{_compact(lot.group(1))}:{lot.group(2)}"
    return None


def _in_korea(latitude: float, longitude: float) -> bool:
    return 33 <= latitude <= 39 and 124 <= longitude <= 132


def _naver_geocode(address: str, env: dict[str, str | None]) -> tuple[float, float, str] | None:
    client_id = (env.get("NAVER_MAP_CLIENT_ID") or "").strip()
    secret = (env.get("NAVER_MAP_CLIENT_SECRET") or "").strip()
    if not client_id or not secret:
        return None
    url = (env.get("NAVER_GEOCODING_API_URL") or "https://maps.apigw.ntruss.com/map-geocode/v2/geocode").strip()
    response = httpx.get(
        url,
        params={"query": address},
        headers={"x-ncp-apigw-api-key-id": client_id, "x-ncp-apigw-api-key": secret},
        timeout=15,
        trust_env=False,
    )
    if response.status_code == 403:
        raise PermissionError("NAVER Geocoding 권한이 비활성화되어 있습니다.")
    response.raise_for_status()
    rows = response.json().get("addresses") or []
    if len(rows) != 1:
        return None
    row = rows[0]
    latitude, longitude = float(row["y"]), float(row["x"])
    if not _in_korea(latitude, longitude):
        return None
    return latitude, longitude, str(row.get("roadAddress") or row.get("jibunAddress") or address)


def _record(connection: sqlite3.Connection, complex_id: str, latitude: float, longitude: float, method: str, source: str, confidence: float) -> None:
    now = datetime.now(UTC).isoformat()
    connection.execute(
        """insert or replace into coordinate_corrections
        (complex_id,latitude,longitude,method,source_reference,confidence,corrected_at)
        values (?,?,?,?,?,?,?)""",
        (complex_id, latitude, longitude, method, source, confidence, now),
    )
    connection.execute("update complexes set latitude=?,longitude=? where complex_id=?", (latitude, longitude, complex_id))
    connection.execute("update complex_data_links set latitude=?,longitude=? where complex_id=?", (latitude, longitude, complex_id))
    connection.execute(
        """update seoul_complex_profiles set latitude=?,longitude=?,validation_status='VALIDATED',
        eligibility_reason='검증된 주소 기반 좌표 보정',updated_at=? where complex_id=?""",
        (latitude, longitude, now, complex_id),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="단지 좌표 고신뢰 보정")
    parser.add_argument("--naver", action="store_true", help="고신뢰 로컬 매칭 후 NAVER Geocoding 사용")
    args = parser.parse_args()
    if not LINKAGE_PATH.exists():
        raise FileNotFoundError(LINKAGE_PATH)

    connection = sqlite3.connect(DB_PATH)
    connection.execute(
        """create table if not exists coordinate_corrections (
        complex_id text primary key, latitude real not null, longitude real not null,
        method text not null, source_reference text not null, confidence real not null,
        corrected_at text not null)"""
    )
    missing = pd.read_sql_query(
        """select complex_id,complex_name,address from seoul_complex_profiles
        where latitude is null or longitude is null""",
        connection,
    )
    sources = pd.read_parquet(LINKAGE_PATH).dropna(subset=["latitude", "longitude"]).copy()
    source_index: dict[tuple[str, str], list[pd.Series]] = {}
    for _, row in sources.iterrows():
        key = _address_key(row["address"])
        if key:
            source_index.setdefault(key, []).append(row)

    corrected: set[str] = set()
    for _, row in missing.iterrows():
        key = _address_key(row["address"])
        candidates = source_index.get(key, []) if key else []
        unique_coordinates = {(round(float(x["latitude"]), 7), round(float(x["longitude"]), 7)) for x in candidates}
        if len(unique_coordinates) != 1:
            continue
        latitude, longitude = next(iter(unique_coordinates))
        source = next(x for x in candidates if round(float(x["latitude"]), 7) == latitude and round(float(x["longitude"]), 7) == longitude)
        _record(connection, row["complex_id"], latitude, longitude, f"verified_{key[0]}_address", str(source["address"]), 1.0)
        corrected.add(row["complex_id"])

    naver_corrected = 0
    naver_error: str | None = None
    if args.naver:
        env = dotenv_values(ROOT / ".env")
        for _, row in missing.loc[~missing["complex_id"].isin(corrected)].iterrows():
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
                _record(connection, row["complex_id"], latitude, longitude, "naver_geocoding_unique", matched_address, 0.95)
                naver_corrected += 1
    connection.commit()
    remaining = connection.execute(
        "select count(*) from seoul_complex_profiles where latitude is null or longitude is null"
    ).fetchone()[0]
    connection.close()
    print({
        "missing_before": len(missing),
        "verified_local_corrected": len(corrected),
        "naver_corrected": naver_corrected,
        "remaining": remaining,
        "naver_status": naver_error or ("NOT_REQUESTED" if not args.naver else "COMPLETE"),
    })


if __name__ == "__main__":
    main()
