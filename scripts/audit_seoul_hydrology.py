"""Print reproducible local/DB QA for the seven Seoul hydrology datasets."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.base import FloodSpatialFeature, SeoulComplexProfile
from backend.app.db.session import SessionLocal
from backend.app.services.flood_spatial_feature_service import dataset_availability


def main() -> None:
    datasets = dataset_availability(ROOT)
    with SessionLocal() as db:
        summary = {
            "complexes": db.scalar(select(func.count()).select_from(SeoulComplexProfile)),
            "spatial_features": db.scalar(select(func.count()).select_from(FloodSpatialFeature)),
            "coordinate_blocked": db.scalar(
                select(func.count()).select_from(SeoulComplexProfile).where(
                    (SeoulComplexProfile.latitude.is_(None)) | (SeoulComplexProfile.longitude.is_(None))
                )
            ),
            "rain_station_linked": db.scalar(
                select(func.count()).select_from(FloodSpatialFeature).where(
                    FloodSpatialFeature.nearest_rain_station_id.is_not(None)
                )
            ),
            "river_station_linked": db.scalar(
                select(func.count()).select_from(FloodSpatialFeature).where(
                    FloodSpatialFeature.nearest_river_station_id.is_not(None)
                )
            ),
            "pump_linked": db.scalar(
                select(func.count()).select_from(FloodSpatialFeature).where(
                    FloodSpatialFeature.distance_to_nearest_pump_station_m.is_not(None)
                )
            ),
            "historical_flood_features": db.scalar(
                select(func.count()).select_from(FloodSpatialFeature).where(
                    FloodSpatialFeature.historical_flood_overlap.is_not(None)
                )
            ),
            "expected_flood_features": db.scalar(
                select(func.count()).select_from(FloodSpatialFeature).where(
                    FloodSpatialFeature.expected_flood_overlap.is_not(None)
                )
            ),
        }
    print(json.dumps({"datasets": datasets, "linkage": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
