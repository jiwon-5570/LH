"""Collect configured Seoul hydrology APIs, then rebuild complex features."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.collectors.pipeline import ingest
from backend.app.collectors.registry import get_dataset
from backend.app.db.base import Base
from backend.app.db.session import SessionLocal, engine
from backend.app.services.flood_spatial_feature_service import build_flood_spatial_features
from backend.app.services.flood_trace_service import consolidate_mois_api_flood_traces

DATASETS = (
    "mois_flood_trace_api",
    "seoul_flood_forecast_geometry",
    "seoul_pump_station_attributes",
    "seoul_river_levels",
)


def _recent_snapshot(dataset_id: str, minimum_interval_minutes: int) -> Path | None:
    if minimum_interval_minutes <= 0:
        return None
    files = list((ROOT / "data" / "processed" / dataset_id).glob("*.parquet"))
    if not files:
        return None
    latest = max(files, key=lambda path: path.stat().st_mtime)
    age_seconds = datetime.now(UTC).timestamp() - latest.stat().st_mtime
    return latest if age_seconds < minimum_interval_minutes * 60 else None


def main() -> None:
    parser = argparse.ArgumentParser(description="서울 수문 OpenAPI 증분 수집")
    parser.add_argument("--force", action="store_true", help="최근 수집본이 있어도 다시 수집")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=True)
    Base.metadata.create_all(engine)
    results: dict[str, dict] = {}
    minimum_interval = max(0, int(os.getenv("HYDROLOGY_COLLECTION_MIN_INTERVAL_MINUTES", "60")))
    for dataset_id in DATASETS:
        spec = get_dataset(dataset_id)
        key = os.getenv(spec.api_key_env or "", "").strip()
        url = os.getenv(spec.api_url_env or "", "").strip()
        if not key or not url:
            results[dataset_id] = {
                "status": "BLOCKED_BY_CONFIGURATION",
                "missing": [
                    name for name, value in (
                        (spec.api_key_env, key), (spec.api_url_env, url)
                    ) if name and not value
                ],
            }
            continue
        recent = None if args.force else _recent_snapshot(dataset_id, minimum_interval)
        if recent:
            results[dataset_id] = {
                "status": "SKIPPED_RECENT",
                "processed_path": str(recent),
                "minimum_interval_minutes": minimum_interval,
            }
            continue
        try:
            collected = ingest(dataset_id)
            results[dataset_id] = {"status": "SUCCESS", **collected}
            if dataset_id == "mois_flood_trace_api":
                canonical_path = ROOT / "data/processed/seoul_flood_trace/seoul_flood_trace.parquet"
                results[dataset_id]["spatial_integration"] = consolidate_mois_api_flood_traces(
                    Path(collected["processed_path"]),
                    canonical_path if canonical_path.exists() else None,
                    canonical_path.parent,
                )
        # Isolate independent public APIs so one outage does not hide the others.
        except Exception as exc:  # noqa: BLE001
            results[dataset_id] = {"status": "FAILED", "reason": str(exc)}
    with SessionLocal() as db:
        feature_result = build_flood_spatial_features(db, ROOT)
    print(json.dumps({"collections": results, "features": feature_result}, ensure_ascii=False, indent=2))
    if any(item["status"] == "FAILED" for item in results.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
