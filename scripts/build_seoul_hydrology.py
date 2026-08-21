"""Build canonical Seoul hydrology files and compact per-complex features."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.base import Base, DataCollectionRun
from backend.app.db.session import SessionLocal, engine
from backend.app.services.flood_spatial_feature_service import build_flood_spatial_features
from backend.app.services.flood_trace_service import (
    consolidate_flood_traces,
    consolidate_mois_api_flood_traces,
)


def main() -> None:
    Base.metadata.create_all(engine)
    flood_paths = sorted((ROOT / "data/processed/mois_flood_trace").glob("*.parquet"))
    canonical = consolidate_flood_traces(
        flood_paths, ROOT / "data/processed/seoul_flood_trace"
    ) if flood_paths else {"status": "BLOCKED_BY_DATA", "output_features": 0}
    api_paths = sorted(
        (ROOT / "data/processed/mois_flood_trace_api").glob("*.parquet"),
        key=lambda path: path.stat().st_mtime,
    )
    if api_paths:
        canonical_path = ROOT / "data/processed/seoul_flood_trace/seoul_flood_trace.parquet"
        canonical["mois_api_integration"] = consolidate_mois_api_flood_traces(
            api_paths[-1], canonical_path if canonical_path.exists() else None, canonical_path.parent
        )
    now = datetime.now(UTC)
    with SessionLocal() as db:
        feature_summary = build_flood_spatial_features(db, ROOT)
        for dataset_id, details in feature_summary["dataset_availability"].items():
            db.merge(DataCollectionRun(
                collection_run_id=f"seoul-hydrology-{dataset_id}-{now:%Y%m%d%H%M%S}",
                dataset_id=dataset_id,
                source_name=dataset_id,
                started_at=now,
                finished_at=now,
                status="complete" if details["status"] == "AVAILABLE" else "partial",
                raw_path=str(ROOT / "data/raw" / dataset_id),
                processed_path=str(ROOT / "data/processed" / dataset_id),
                record_count=details["record_count"],
                valid_count=details["record_count"],
                quarantined_count=0,
                failure_reason=details.get("blocking_reason"),
                data_version=details["data_version"],
            ))
        db.commit()
    print(json.dumps({"flood_trace": canonical, "features": feature_summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
