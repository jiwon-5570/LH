"""Collect and spatially integrate MOIS flood-trace API data for Seoul."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.collectors.pipeline import ingest
from backend.app.services.flood_trace_service import consolidate_mois_api_flood_traces

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="행정안전부 침수흔적도 API 수집·서울 공간자료 통합")
    parser.add_argument("--max-pages", type=int, default=100, help="수집할 최대 페이지 수")
    parser.add_argument(
        "--skip-collect", action="store_true", help="최신 적재 파일로 공간 통합만 다시 수행"
    )
    args = parser.parse_args()

    processed_dir = ROOT / "data/processed/mois_flood_trace_api"
    if args.skip_collect:
        paths = sorted(processed_dir.glob("*.parquet"), key=lambda path: path.stat().st_mtime)
        if not paths:
            raise FileNotFoundError("적재된 행정안전부 침수흔적도 API Parquet이 없습니다.")
        api_path = paths[-1]
        result: dict = {"processed_path": str(api_path), "collection": "SKIPPED"}
    else:
        result = ingest("mois_flood_trace_api", max_pages=args.max_pages)
        api_path = Path(result["processed_path"])

    canonical_dir = ROOT / "data/processed/seoul_flood_trace"
    canonical_path = canonical_dir / "seoul_flood_trace.parquet"
    result["spatial_integration"] = consolidate_mois_api_flood_traces(
        api_path,
        canonical_path if canonical_path.exists() else None,
        canonical_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
