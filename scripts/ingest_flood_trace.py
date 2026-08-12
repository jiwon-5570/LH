"""Ingest an approved MOIS flood trace SHP/GPKG/GeoJSON/ZIP without guessing CRS."""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.app.services.flood_trace_service import process_flood_trace


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("file",type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    print(process_flood_trace(args.file,root/"data/raw/mois_flood_trace",root/"data/staging/mois_flood_trace",root/"data/processed/mois_flood_trace",root/"data/quarantine/mois_flood_trace"))


if __name__ == "__main__": main()
