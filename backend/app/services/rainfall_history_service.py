from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _station_id(name: str) -> str:
    return "derived-" + hashlib.sha1(name.strip().encode("utf-8")).hexdigest()[:12]


def _sample_positive(values: pd.Series, limit: int = 5000) -> list[float]:
    positive = values[(values > 0) & values.notna()].to_numpy(dtype=float)
    if len(positive) <= limit:
        return positive.tolist()
    step = math.ceil(len(positive) / limit)
    return positive[::step][:limit].tolist()


def _rolling_sum(frame: pd.DataFrame, minutes: int, expected_count: int) -> pd.Series:
    indexed = frame.set_index("observed_at")["rainfall_mm"].sort_index()
    rolling = indexed.rolling(f"{minutes}min")
    values = rolling.sum()
    return values.where(rolling.count() >= expected_count)


def empirical_rain_index(value: float | None, reference: dict | None) -> float | None:
    """Map rainfall to an empirical positive-rain percentile scale, not probability."""
    if value is None or reference is None:
        return None
    if value <= 0:
        return 0.0
    points = [(0.0, 0.0)]
    for key, score in (("p50", 50.0), ("p90", 90.0), ("p95", 95.0), ("p99", 99.0), ("p99_9", 100.0)):
        raw = reference.get(key)
        if raw is not None and float(raw) > points[-1][0]:
            points.append((float(raw), score))
    if len(points) == 1:
        return None
    return round(float(np.interp(value, [point[0] for point in points], [point[1] for point in points])), 2)


def ingest_rainfall_history(source: Path, root: Path) -> dict:
    version = _sha256(source)
    raw_dir = root / "data/raw/seoul_rainfall_history"
    processed_dir = root / "data/processed/seoul_rainfall_history" / version[:12]
    quarantine_dir = root / "data/quarantine/seoul_rainfall_history" / version[:12]
    for directory in (raw_dir, processed_dir, quarantine_dir):
        directory.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / source.name
    if source.resolve() != raw_path.resolve():
        shutil.copy2(source, raw_path)

    summaries: list[dict] = []
    distributions: dict[str, list[float]] = {"10m":[], "1h":[], "3h":[], "24h":[]}
    total_input = total_valid = total_invalid = total_duplicates = 0
    with zipfile.ZipFile(raw_path, metadata_encoding="cp949") as archive:
        members = [member for member in archive.infolist() if member.filename.lower().endswith(".csv")]
        if not members:
            raise ValueError("ZIP 내부에 CSV가 없습니다.")
        for member in members:
            with archive.open(member) as handle:
                frame = pd.read_csv(handle, encoding="cp949")
            total_input += len(frame)
            required = {"강우량계명", "시간", "10분우량"}
            if not required.issubset(frame.columns):
                raise ValueError(f"필수 컬럼 누락({member.filename}): {sorted(required - set(frame.columns))}")
            normalized = frame.rename(columns={"강우량계명":"station_name", "시간":"observed_at", "10분우량":"rainfall_mm"})[["station_name", "observed_at", "rainfall_mm"]].copy()
            normalized["observed_at"] = pd.to_datetime(normalized["observed_at"], errors="coerce")
            normalized["rainfall_mm"] = pd.to_numeric(normalized["rainfall_mm"], errors="coerce")
            invalid_mask = normalized["station_name"].isna() | normalized["observed_at"].isna() | normalized["rainfall_mm"].isna() | (normalized["rainfall_mm"] < 0) | (normalized["rainfall_mm"] > 100)
            invalid = normalized.loc[invalid_mask].copy()
            invalid["invalid_reason"] = "MISSING_OR_NEGATIVE"
            invalid.loc[invalid["rainfall_mm"] > 100, "invalid_reason"] = "EXTREME_OVER_100MM_10MIN_REVIEW_REQUIRED"
            valid = normalized.loc[~invalid_mask].copy()
            duplicate_mask = valid.duplicated(["station_name", "observed_at"], keep="last")
            duplicate_count = int(duplicate_mask.sum())
            valid = valid.loc[~duplicate_mask].sort_values("observed_at")
            year_match = re.search(r"(?:19|20)\d{2}", member.filename)
            source_year = int(year_match.group()) if year_match else int(valid["observed_at"].dt.year.mode().iloc[0])
            mismatched_year = int((valid["observed_at"].dt.year != source_year).sum())
            if mismatched_year:
                invalid = pd.concat([invalid, valid[valid["observed_at"].dt.year != source_year]], ignore_index=True)
                valid = valid[valid["observed_at"].dt.year == source_year]
            station_name = str(valid["station_name"].mode().iloc[0]).strip()
            station_id = _station_id(station_name)
            valid["observed_at"] = valid["observed_at"].dt.tz_localize("Asia/Seoul").dt.tz_convert("UTC")
            valid["station_id"] = station_id
            valid["source_year"] = source_year
            valid["source_file"] = member.filename
            valid["data_version"] = version
            valid["station_id_provenance"] = "derived_from_station_name"
            output_dir = processed_dir / f"year={source_year}"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{station_id}.parquet"
            valid.to_parquet(output_path, index=False)
            if not invalid.empty:
                invalid.to_parquet(quarantine_dir / f"{source_year}_{station_id}.parquet", index=False)

            roll_1h = _rolling_sum(valid, 60, 6)
            roll_3h = _rolling_sum(valid, 180, 18)
            roll_24h = _rolling_sum(valid, 1440, 144)
            distributions["10m"].extend(_sample_positive(valid["rainfall_mm"]))
            distributions["1h"].extend(_sample_positive(roll_1h))
            distributions["3h"].extend(_sample_positive(roll_3h))
            distributions["24h"].extend(_sample_positive(roll_24h))
            expected = 52704 if pd.Timestamp(source_year, 12, 31).is_leap_year else 52560
            completeness = min(1.0, len(valid) / expected)
            summaries.append({
                "station_id":station_id, "station_name":station_name, "source_year":source_year,
                "observed_from":None if valid.empty else valid["observed_at"].min(),
                "observed_until":None if valid.empty else valid["observed_at"].max(),
                "record_count":len(valid), "duplicate_count":duplicate_count,
                "invalid_count":len(invalid), "completeness_ratio":round(completeness, 6),
                "rainfall_total_mm":round(float(valid["rainfall_mm"].sum()), 3),
                "max_10m_mm":round(float(valid["rainfall_mm"].max()), 3),
                "max_1h_mm":None if roll_1h.dropna().empty else round(float(roll_1h.max()), 3),
                "max_3h_mm":None if roll_3h.dropna().empty else round(float(roll_3h.max()), 3),
                "max_24h_mm":None if roll_24h.dropna().empty else round(float(roll_24h.max()), 3),
                "data_version":version, "processed_at":datetime.now(UTC),
                "data_quality_status":"COMPLETE" if completeness >= 0.9 else "PARTIAL_INTERVALS",
            })
            total_valid += len(valid)
            total_invalid += len(invalid)
            total_duplicates += duplicate_count

    summary = pd.DataFrame(summaries)
    summary_path = processed_dir / "station_year_statistics.parquet"
    summary.to_parquet(summary_path, index=False)
    references: dict[str, dict] = {}
    for window, values in distributions.items():
        array = np.asarray(values, dtype=float)
        exact_max_column = {"10m":"max_10m_mm", "1h":"max_1h_mm", "3h":"max_3h_mm", "24h":"max_24h_mm"}[window]
        exact_max = pd.to_numeric(summary[exact_max_column], errors="coerce").max()
        references[window] = {
            "positive_sample_count":len(array),
            "p50":None if not len(array) else round(float(np.quantile(array, 0.5)), 3),
            "p90":None if not len(array) else round(float(np.quantile(array, 0.9)), 3),
            "p95":None if not len(array) else round(float(np.quantile(array, 0.95)), 3),
            "p99":None if not len(array) else round(float(np.quantile(array, 0.99)), 3),
            "p99_9":None if not len(array) else round(float(np.quantile(array, 0.999)), 3),
            "max":None if pd.isna(exact_max) else round(float(exact_max), 3),
        }
    partial_count = int((summary["data_quality_status"] != "COMPLETE").sum())
    reference_payload = {
        "status":"COMPLETE" if partial_count == 0 else "PARTIAL_COVERAGE", "source_years":sorted(summary["source_year"].unique().tolist()),
        "station_count":int(summary["station_id"].nunique()), "station_year_files":len(summary),
        "complete_station_years":int((summary["data_quality_status"] == "COMPLETE").sum()),
        "partial_station_years":partial_count,
        "mean_completeness_ratio":round(float(summary["completeness_ratio"].mean()), 6),
        "data_version":version, "method":"positive-rain empirical quantiles; per-file deterministic sample capped at 5000; maxima exact",
        "references":references, "created_at":datetime.now(UTC).isoformat(),
    }
    reference_path = processed_dir / "rainfall_reference.json"
    reference_path.write_text(json.dumps(reference_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "status":reference_payload["status"], "source_files":len(summaries), "stations":int(summary["station_id"].nunique()),
        "source_years":reference_payload["source_years"], "input_records":total_input,
        "valid_records":total_valid, "invalid_records":total_invalid, "duplicate_records":total_duplicates,
        "summary_path":str(summary_path), "reference_path":str(reference_path), "data_version":version,
    }
