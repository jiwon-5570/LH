from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import rasterio
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
MODEL_VERSION = "operational-screening-v1"


def level(probability: float) -> str:
    if probability >= 0.85: return "매우 높음"
    if probability >= 0.70: return "높음"
    if probability >= 0.45: return "보통"
    return "낮음"


def sample_elevations(frame: pd.DataFrame) -> dict[str, float]:
    result: dict[str, float] = {}
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True)
    rasters = list((ROOT / "data" / "incoming" / "ngii_dem").glob("*.img"))
    datasets = [rasterio.open(path) for path in rasters]
    try:
        for row in frame.dropna(subset=["latitude", "longitude"]).itertuples():
            x, y = transformer.transform(float(row.longitude), float(row.latitude))
            for dataset in datasets:
                if dataset.bounds.left <= x <= dataset.bounds.right and dataset.bounds.bottom <= y <= dataset.bounds.top:
                    value = float(next(dataset.sample([(x, y)]))[0])
                    if value != dataset.nodata and math.isfinite(value): result[str(row.complex_id)] = value
                    break
    finally:
        for dataset in datasets: dataset.close()
    return result


def environmental_factors() -> tuple[float, float, dict]:
    rain_paths = list((ROOT / "data" / "processed" / "seoul_rainfall").glob("*.parquet"))
    sewer_paths = list((ROOT / "data" / "processed" / "seoul_sewer_level").glob("*.parquet"))
    rain_factor = sewer_factor = 0.0; metadata = {}
    if rain_paths:
        rain = pd.read_parquet(max(rain_paths, key=lambda p:p.stat().st_size), columns=["observed_at", "rainfall_mm"])
        rain["rainfall_mm"] = pd.to_numeric(rain["rainfall_mm"], errors="coerce")
        latest = rain["observed_at"].max(); current = rain[rain["observed_at"] == latest]["rainfall_mm"]
        rainfall = float(current.max()) if not current.empty and current.notna().any() else 0.0
        rain_factor = min(max(rainfall / 30.0, 0.0), 1.0); metadata.update({"rain_observed_at":str(latest),"rainfall_mm":rainfall})
    if sewer_paths:
        sewer = pd.read_parquet(max(sewer_paths, key=lambda p:p.stat().st_size), columns=["observed_at", "water_level"])
        sewer["water_level"] = pd.to_numeric(sewer["water_level"], errors="coerce")
        latest = sewer["observed_at"].max(); current = sewer[sewer["observed_at"] == latest]["water_level"].dropna()
        water = float(current.max()) if not current.empty else 0.0
        reference = float(sewer["water_level"].quantile(.95)) if sewer["water_level"].notna().any() else 1.0
        sewer_factor = min(max(water / reference, 0.0), 1.0) if reference > 0 else 0.0
        metadata.update({"sewer_observed_at":str(latest),"sewer_level":water,"sewer_p95":reference})
    return rain_factor, sewer_factor, metadata


def main() -> None:
    con = sqlite3.connect(ROOT / "lh_predict.db")
    links = pd.read_sql_query("select c.complex_id,c.complex_name,c.address,l.* from complexes c join complex_data_links l on c.complex_id=l.complex_id", con)
    elevations = sample_elevations(links)
    rain_factor, sewer_factor, environment = environmental_factors()
    now = datetime.now(UTC); now_text = now.isoformat()
    predictions = []; alerts = []

    for row in links.itertuples():
        if row.elevator_count > 0:
            corrective_rate = min(row.corrective_count / max(row.elevator_count, 1), 1.0)
            probability = min(.97, .12 + (.38 if row.corrective_count > 0 else 0) + .42 * corrective_rate)
            snapshot = {
                "method": "운영 선별지수",
                "elevator_count": row.elevator_count,
                "corrective_count": row.corrective_count,
                "corrective_rate": round(corrective_rate, 4),
                "components": {
                    "base": 0.12,
                    "corrective_history": 0.38 if row.corrective_count > 0 else 0.0,
                    "corrective_rate": round(0.42 * corrective_rate, 4),
                },
                "formula": "min(0.97, 0.12 + 시정권고이력 0.38 + 시정권고비율×0.42)",
                "ml_model": False,
            }
            predictions.append((f"facility-{row.complex_id}-{now.strftime('%Y%m%d%H%M')}",row.complex_id,"facility",MODEL_VERSION,now_text,now_text,probability,level(probability),json.dumps(snapshot,ensure_ascii=False),"linked" ,now_text))

        elevation = elevations.get(str(row.complex_id))
        if elevation is not None:
            elevation_factor = min(max((35.0 - elevation) / 35.0, 0.0), 1.0)
            probability = min(.97, .08 + .40*rain_factor + .32*sewer_factor + .20*elevation_factor)
            snapshot = {
                "method": "운영 선별지수",
                "elevation_m": round(elevation, 2),
                "elevation_factor": round(elevation_factor, 4),
                "rain_factor": round(rain_factor, 4),
                "sewer_factor": round(sewer_factor, 4),
                **environment,
                "components": {
                    "base": 0.08,
                    "rain": round(0.40 * rain_factor, 4),
                    "sewer_level": round(0.32 * sewer_factor, 4),
                    "low_elevation": round(0.20 * elevation_factor, 4),
                },
                "formula": "min(0.97, 0.08 + 강우지수×0.40 + 하수수위지수×0.32 + 저지대지수×0.20)",
                "ml_model": False,
            }
            predictions.append((f"flood-{row.complex_id}-{now.strftime('%Y%m%d%H%M')}",row.complex_id,"flood",MODEL_VERSION,now_text,now_text,probability,level(probability),json.dumps(snapshot,ensure_ascii=False),"linked",now_text))

    for prediction in predictions:
        if prediction[6] >= .70:
            risk_name = "침수" if prediction[2] == "flood" else "설비"
            alert_id = hashlib.sha256(f"{prediction[0]}|alert".encode()).hexdigest()[:32]
            alerts.append((alert_id,prediction[1],prediction[2],prediction[7],f"{risk_name} 운영 선별지수 {prediction[6]*100:.1f}% · 현장 점검 필요",0,now_text))

    con.execute("delete from predictions where model_version=?", (MODEL_VERSION,))
    con.executemany("insert into predictions (prediction_id,complex_id,risk_type,model_version,prediction_time,target_time,risk_probability,risk_level,feature_snapshot,data_quality_status,created_at) values (?,?,?,?,?,?,?,?,?,?,?)",predictions)
    con.execute("delete from alerts where alert_id like ?", ("%",))
    con.executemany("insert into alerts (alert_id,complex_id,risk_type,risk_level,summary,acknowledged,created_at) values (?,?,?,?,?,?,?)",alerts)
    con.commit(); con.close()
    print({"predictions":len(predictions),"alerts":len(alerts),"facility":sum(p[2]=='facility' for p in predictions),"flood":sum(p[2]=='flood' for p in predictions),"model_version":MODEL_VERSION,"ml_model":False})


if __name__ == "__main__": main()
