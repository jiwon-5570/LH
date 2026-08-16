"""Collect approved MOIS flood-trace attributes from Safety Data Platform."""

from __future__ import annotations

import argparse
import json

from backend.app.collectors.pipeline import ingest


def main() -> None:
    parser = argparse.ArgumentParser(description="행정안전부 침수흔적도 승인 API 수집")
    parser.add_argument("--max-pages", type=int, default=100, help="안전한 최대 페이지 수")
    args = parser.parse_args()
    result = ingest("mois_flood_trace_api", max_pages=args.max_pages)
    result["spatial_geometry_status"] = "BLOCKED_BY_DATA"
    result["note"] = "이 API는 SN/FLDN_DOWA 속성만 제공합니다. 공간 모델에는 별도 SHP/GPKG가 필요합니다."
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
