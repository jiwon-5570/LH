"""Ingest Seoul 2021-2024 ten-minute rainfall history and empirical references."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

import pandas as pd
from sqlalchemy import delete

from backend.app.db.base import Base, RainfallHistoricalStatistic
from backend.app.db.session import SessionLocal, engine
from backend.app.services.rainfall_history_service import ingest_rainfall_history

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="서울시 10분 강우량 과거자료 적재")
    parser.add_argument("file", type=Path, nargs="?")
    args = parser.parse_args()
    if args.file:
        result = ingest_rainfall_history(args.file, ROOT)
    else:
        summaries = list((ROOT / "data/processed/seoul_rainfall_history").glob("*/station_year_statistics.parquet"))
        if not summaries:
            raise FileNotFoundError("적재된 서울시 과거 강우량 통계가 없습니다.")
        summary_path = max(summaries, key=lambda path:path.stat().st_mtime)
        reference_path = summary_path.parent / "rainfall_reference.json"
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
        result = {
            "status":"COMPLETE", "summary_path":str(summary_path), "reference_path":str(reference_path),
            "stations":reference["station_count"], "source_years":reference["source_years"],
            "data_version":reference["data_version"],
        }
    summary = pd.read_parquet(result["summary_path"])
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.execute(delete(RainfallHistoricalStatistic))
        for row in summary.to_dict("records"):
            db.add(RainfallHistoricalStatistic(
                rainfall_historical_statistic_id=uuid.uuid4().hex,
                **row,
            ))
        db.commit()
    result["db_statistics"] = len(summary)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
