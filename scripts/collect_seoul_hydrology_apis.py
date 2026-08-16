"""Collect configured Seoul hydrology APIs, then rebuild complex features."""

from __future__ import annotations

import json
import os
import sys
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

DATASETS = (
    "seoul_flood_forecast_geometry",
    "seoul_rain_gauge_locations",
    "seoul_pump_station_attributes",
    "seoul_river_levels",
)


def main() -> None:
    load_dotenv(ROOT / ".env", override=True)
    Base.metadata.create_all(engine)
    results: dict[str, dict] = {}
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
        try:
            results[dataset_id] = {"status": "SUCCESS", **ingest(dataset_id)}
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
