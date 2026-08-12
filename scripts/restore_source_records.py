"""Restore archived source records into SQLite for audit or migration."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pyarrow.parquet as pq

COLUMNS = [
    "source_record_key", "dataset_id", "source_record_id", "collection_run_id",
    "payload", "data_version", "validation_status", "collected_at",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("lh_predict.db"))
    parser.add_argument("--archive-dir", type=Path, default=Path("data/archive/source_records"))
    parser.add_argument("--dataset")
    args = parser.parse_args()
    paths = [args.archive_dir / f"{args.dataset}.parquet"] if args.dataset else sorted(args.archive_dir.glob("*.parquet"))
    con = sqlite3.connect(args.database)
    sql = f"INSERT OR IGNORE INTO source_records ({','.join(COLUMNS)}) VALUES ({','.join('?' for _ in COLUMNS)})"
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
        restored = 0
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(batch_size=20_000, columns=COLUMNS):
            records = batch.to_pylist()
            con.executemany(sql, [tuple(record[column] for column in COLUMNS) for record in records])
            con.commit()
            restored += len(records)
        print(f"restored {path.stem}: {restored:,} archived rows processed")
    con.close()


if __name__ == "__main__":
    main()
