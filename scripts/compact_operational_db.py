"""Archive full source_records to Parquet and compact the operational SQLite DB."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

COLUMNS = [
    "source_record_key", "dataset_id", "source_record_id", "collection_run_id",
    "payload", "data_version", "validation_status", "collected_at",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive(db_path: Path, archive_dir: Path, batch_size: int = 50_000) -> dict:
    archive_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    datasets = con.execute(
        "SELECT dataset_id, COUNT(*) FROM source_records GROUP BY dataset_id ORDER BY dataset_id"
    ).fetchall()
    manifest = {
        "format": "lh-predict-source-records-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "source_database": str(db_path.resolve()),
        "total_records": sum(row[1] for row in datasets),
        "datasets": [],
    }
    for dataset_id, expected in datasets:
        path = archive_dir / f"{dataset_id}.parquet"
        temp = path.with_suffix(".parquet.tmp")
        if temp.exists():
            temp.unlink()
        cursor = con.execute(
            f"SELECT {','.join(COLUMNS)} FROM source_records WHERE dataset_id=? ORDER BY collected_at, source_record_key",
            (dataset_id,),
        )
        writer = None
        written = 0
        try:
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                table = pa.Table.from_pylist([dict(zip(COLUMNS, row)) for row in rows])
                if writer is None:
                    writer = pq.ParquetWriter(temp, table.schema, compression="zstd", compression_level=9)
                writer.write_table(table)
                written += len(rows)
        finally:
            if writer:
                writer.close()
        if written != expected:
            raise RuntimeError(f"{dataset_id}: expected {expected}, archived {written}")
        if path.exists():
            path.unlink()
        temp.replace(path)
        parquet_rows = pq.ParquetFile(path).metadata.num_rows
        if parquet_rows != expected:
            raise RuntimeError(f"{dataset_id}: Parquet verification failed")
        manifest["datasets"].append({
            "dataset_id": dataset_id,
            "records": expected,
            "file": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
        print(f"archived {dataset_id}: {expected:,} rows -> {path.stat().st_size / 1024 / 1024:.1f} MB")
    con.close()
    manifest_path = archive_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def prune_and_compact(db_path: Path, sample_limit: int) -> tuple[int, int]:
    con = sqlite3.connect(db_path)
    before = con.execute("SELECT COUNT(*) FROM source_records").fetchone()[0]
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("BEGIN IMMEDIATE")
    con.execute(
        """DELETE FROM source_records WHERE source_record_key IN (
        SELECT source_record_key FROM (
          SELECT source_record_key,
                 ROW_NUMBER() OVER (PARTITION BY dataset_id ORDER BY collected_at DESC, source_record_key DESC) AS rn
          FROM source_records
        ) WHERE rn > ?)
        """,
        (sample_limit,),
    )
    con.commit()
    after = con.execute("SELECT COUNT(*) FROM source_records").fetchone()[0]
    con.close()

    compact = db_path.with_suffix(".compacted.db")
    if compact.exists():
        compact.unlink()
    con = sqlite3.connect(db_path)
    escaped = str(compact.resolve()).replace("'", "''")
    con.execute(f"VACUUM INTO '{escaped}'")
    con.close()
    check = sqlite3.connect(compact)
    integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
    retained = check.execute("SELECT COUNT(*) FROM source_records").fetchone()[0]
    check.close()
    if integrity != "ok" or retained != after:
        raise RuntimeError(f"compacted DB verification failed: {integrity}, {retained}/{after}")
    backup = db_path.with_suffix(".precompact.db")
    if backup.exists():
        backup.unlink()
    shutil.move(db_path, backup)
    shutil.move(compact, db_path)
    print(f"database compacted: {before:,} -> {after:,} source samples")
    print(f"temporary rollback copy: {backup}")
    return before, after


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("lh_predict.db"))
    parser.add_argument("--archive-dir", type=Path, default=Path("data/archive/source_records"))
    parser.add_argument("--sample-limit", type=int, default=100)
    parser.add_argument("--archive-only", action="store_true")
    parser.add_argument("--skip-archive", action="store_true")
    args = parser.parse_args()
    if args.skip_archive:
        manifest_path = args.archive_dir / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeError("verified archive manifest is required before pruning")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = archive(args.database, args.archive_dir)
        print(f"verified archive: {manifest['total_records']:,} rows")
    if not args.archive_only:
        prune_and_compact(args.database, max(0, args.sample_limit))


if __name__ == "__main__":
    main()
