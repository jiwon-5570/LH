"""Build complex-level exposure evidence from ingested Seoul flood-trace polygons."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select

from backend.app.db.base import Base, HistoricalFloodFeature, SeoulComplexProfile
from backend.app.db.session import SessionLocal, engine
from backend.app.services.historical_flood_service import analyze_complex, flood_data_version, load_flood_traces

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_YEARS = set(range(2020, 2026))


def main() -> None:
    paths = sorted((ROOT / "data/processed/mois_flood_trace").glob("*.parquet"))
    traces = load_flood_traces(paths)
    source_years = sorted({int(year) for year in traces["source_year"].dropna()})
    missing_years = sorted(EXPECTED_YEARS - set(source_years))
    version = flood_data_version(paths)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        profiles = db.scalars(select(SeoulComplexProfile).where(
            SeoulComplexProfile.latitude.is_not(None),
            SeoulComplexProfile.longitude.is_not(None),
        )).all()
        db.execute(delete(HistoricalFloodFeature))
        for profile in profiles:
            values = analyze_complex(traces, float(profile.longitude), float(profile.latitude))
            # The operational FloodSpatialFeature table owns radius counts.
            # Keep this legacy evidence table limited to its declared columns.
            values = {
                key: value for key, value in values.items()
                if key in HistoricalFloodFeature.__table__.columns
            }
            db.add(HistoricalFloodFeature(
                historical_flood_feature_id=uuid.uuid4().hex,
                complex_id=profile.complex_id,
                **values,
                source_years=source_years,
                missing_years=missing_years,
                source_feature_count=len(traces),
                data_version=version,
                processed_at=datetime.now(UTC),
                data_quality_status="COMPLETE" if not missing_years else "PARTIAL_TIME_SERIES",
            ))
        db.commit()
    print({
        "source_files":len(paths), "source_features":len(traces), "source_years":source_years,
        "missing_years":missing_years, "complex_features":len(profiles),
    })


if __name__ == "__main__":
    main()
