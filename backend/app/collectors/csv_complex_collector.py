import argparse
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from backend.app.db.base import Base, Complex
from backend.app.db.session import SessionLocal, engine

REQUIRED = {"complex_id","complex_name","address","latitude","longitude","source_name","source_url","observed_at"}

def ingest(path: Path) -> tuple[int,int]:
    df = pd.read_csv(path, dtype={"complex_id":"string"})
    missing = REQUIRED - set(df.columns)
    if missing: raise ValueError(f"필수 컬럼 누락: {sorted(missing)}")
    df["latitude"] = pd.to_numeric(df.latitude, errors="coerce"); df["longitude"] = pd.to_numeric(df.longitude, errors="coerce")
    valid = df.address.notna() & df.latitude.between(33,39) & df.longitude.between(124,132) & ~df.complex_id.duplicated(keep=False)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    quarantine = df.loc[~valid].copy(); Path("data/quarantine").mkdir(parents=True, exist_ok=True)
    if not quarantine.empty: quarantine.to_csv(f"data/quarantine/complexes_{run_id}.csv", index=False)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for row in df.loc[valid].to_dict("records"):
            item = Complex(complex_id=str(row["complex_id"]), complex_name=row["complex_name"], address=row["address"], latitude=row["latitude"], longitude=row["longitude"], source_name=row["source_name"], source_url=row["source_url"], collected_at=datetime.now(UTC), observed_at=pd.to_datetime(row["observed_at"], utc=True).to_pydatetime(), data_version=hashlib.sha256(path.read_bytes()).hexdigest()[:12], validation_status="valid", collection_run_id=run_id)
            db.merge(item)
        db.commit()
    return int(valid.sum()), int((~valid).sum())

if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("path", type=Path); args=p.parse_args(); print(dict(zip(("loaded","quarantined"), ingest(args.path))))
