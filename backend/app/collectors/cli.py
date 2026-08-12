from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.collectors.pipeline import ingest
from backend.app.collectors.registry import load_registry


def main() -> None:
    parser = argparse.ArgumentParser(description="LH-PREDICT 실제 데이터 수집·검증 CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    run = sub.add_parser("ingest"); run.add_argument("dataset_id"); run.add_argument("--file", type=Path); run.add_argument("--max-pages", type=int, default=100)
    args = parser.parse_args()
    if args.command == "list":
        for spec in load_registry().values(): print(f"{spec.id:32} {spec.mode:12} {spec.name}")
    else:
        print(json.dumps(ingest(args.dataset_id, args.file, args.max_pages), ensure_ascii=False, indent=2))

if __name__ == "__main__": main()
