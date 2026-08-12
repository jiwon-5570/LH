"""Build real 100/300/500 m DEM features for coordinate-validated Seoul LH complexes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select

from backend.app.db.base import Base, SeoulComplexProfile, TerrainFeature
from backend.app.db.session import SessionLocal, engine
from backend.app.services.terrain_service import TerrainAnalyzer

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    paths = sorted((ROOT / "data" / "incoming" / "ngii_dem").glob("*.img"))
    if not paths:
        raise FileNotFoundError("국토지리정보원 DEM IMG가 없습니다")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        profiles = db.scalars(select(SeoulComplexProfile).where(SeoulComplexProfile.latitude.is_not(None), SeoulComplexProfile.longitude.is_not(None))).all()
    rows = []
    with TerrainAnalyzer(paths) as analyzer:
        for profile in profiles:
            values = analyzer.analyze(profile.complex_id, float(profile.longitude), float(profile.latitude))
            values.update({"terrain_feature_id":uuid.uuid4().hex,"processed_at":datetime.now(UTC)})
            rows.append(values)
    with SessionLocal() as db:
        db.execute(delete(TerrainFeature))
        for values in rows:
            db.add(TerrainFeature(**values))
        db.commit()
    print({"dem_sources":len(paths),"profiles_with_coordinates":len(profiles),"terrain_features":len(rows),"complete":sum(row["data_quality_status"]=="COMPLETE" for row in rows),"insufficient":sum(row["data_quality_status"]=="INSUFFICIENT" for row in rows)})


if __name__ == "__main__":
    main()
