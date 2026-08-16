"""Ingest Seoul rain-pump ZIP and build complex proximity evidence."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
from sqlalchemy import delete, select

from backend.app.db.base import Base, RainPumpProximityFeature, SeoulComplexProfile
from backend.app.db.session import SessionLocal, engine
from backend.app.services.rain_pump_service import analyze_complex, ingest_rain_pump

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="서울시 빗물펌프장 공간정보 적재")
    parser.add_argument("file", type=Path, nargs="?")
    args = parser.parse_args()
    if args.file:
        metadata = ingest_rain_pump(args.file, ROOT)
    else:
        paths = sorted((ROOT / "data/processed/seoul_rain_pump").glob("*.parquet"))
        if not paths:
            raise FileNotFoundError("적재된 서울시 빗물펌프장 GeoParquet이 없습니다.")
        processed_path = max(paths, key=lambda path:path.stat().st_mtime)
        metadata_path = processed_path.with_suffix(".metadata.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    pumps = gpd.read_parquet(metadata["processed_path"])
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        profiles = db.scalars(select(SeoulComplexProfile).where(
            SeoulComplexProfile.latitude.is_not(None),
            SeoulComplexProfile.longitude.is_not(None),
        )).all()
        db.execute(delete(RainPumpProximityFeature))
        for profile in profiles:
            values = analyze_complex(pumps, float(profile.longitude), float(profile.latitude))
            db.add(RainPumpProximityFeature(
                rain_pump_proximity_feature_id=uuid.uuid4().hex,
                complex_id=profile.complex_id,
                **values,
                source_feature_count=len(pumps),
                capacity_status="NOT_PROVIDED",
                operation_status="NOT_PROVIDED",
                data_version=metadata["data_version"],
                processed_at=datetime.now(UTC),
                data_quality_status="PARTIAL_ATTRIBUTES",
            ))
        db.commit()
    metadata["complex_features"] = len(profiles)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
