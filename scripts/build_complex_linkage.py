from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def normalize_address(value: object) -> str:
    text = str(value or "").lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    return re.sub(r"[^0-9a-z가-힣]", "", text)


def latest_parquet(dataset_id: str) -> Path:
    paths = list((ROOT / "data" / "processed" / dataset_id).glob("*.parquet"))
    if not paths:
        raise FileNotFoundError(f"{dataset_id} processed parquet 없음")
    return max(paths, key=lambda path: path.stat().st_mtime)


def main() -> None:
    database = ROOT / "lh_predict.db"
    connection = sqlite3.connect(database)
    complexes = pd.read_sql_query(
        "select complex_id,complex_name,address from complexes", connection
    )
    complexes["normalized_address"] = complexes["address"].map(normalize_address)

    coordinates = pd.read_parquet(
        latest_parquet("elevator_building_coordinates"),
        columns=["address", "latitude", "longitude"],
    )
    coordinates["normalized_address"] = coordinates["address"].map(normalize_address)
    coordinates["latitude"] = pd.to_numeric(coordinates["latitude"], errors="coerce")
    coordinates["longitude"] = pd.to_numeric(coordinates["longitude"], errors="coerce")
    coordinate_summary = coordinates.groupby("normalized_address", as_index=False).agg(
        latitude=("latitude", "median"), longitude=("longitude", "median")
    )

    installation_paths = list((ROOT / "data" / "processed" / "elevator_installations").glob("*.parquet"))
    installations = pd.concat(
        [pd.read_parquet(path, columns=["elevator_id", "address", "inspection_history_code"]) for path in installation_paths],
        ignore_index=True,
    )
    installations["normalized_address"] = installations["address"].map(normalize_address)
    wanted_addresses = set(complexes["normalized_address"])
    installations = installations[installations["normalized_address"].isin(wanted_addresses)].copy()
    installations["elevator_id"] = installations["elevator_id"].astype("string")
    installations["inspection_history_code"] = installations["inspection_history_code"].astype("string")
    installation_summary = installations.groupby("normalized_address", as_index=False).agg(
        elevator_count=("elevator_id", "nunique")
    )

    inspections = pd.read_parquet(
        latest_parquet("elevator_inspections"),
        columns=["inspection_history_code", "inspection_date", "inspection_result"],
    )
    history_to_address = installations[["inspection_history_code", "normalized_address"]].dropna().drop_duplicates("inspection_history_code")
    inspections["inspection_history_code"] = inspections["inspection_history_code"].astype("string")
    inspections = inspections.merge(history_to_address, on="inspection_history_code", how="inner")
    result_text = inspections["inspection_result"].fillna("").astype(str)
    inspections["is_fail"] = result_text.str.contains("불합격|부적합", regex=True)
    inspections["is_conditional"] = result_text.str.contains("조건부", regex=False)
    inspection_summary = inspections.groupby("normalized_address", as_index=False).agg(
        inspection_count=("inspection_history_code", "size"),
        inspection_fail_count=("is_fail", "sum"),
        conditional_pass_count=("is_conditional", "sum"),
        last_inspection_date=("inspection_date", "max"),
    )

    actions = pd.read_parquet(
        latest_parquet("elevator_corrective_actions"), columns=["elevator_id"]
    )
    elevator_to_address = installations[["elevator_id", "normalized_address"]].dropna().drop_duplicates("elevator_id")
    actions["elevator_id"] = actions["elevator_id"].astype("string")
    actions = actions.merge(elevator_to_address, on="elevator_id", how="inner")
    corrective_summary = actions.groupby("normalized_address", as_index=False).agg(
        corrective_count=("elevator_id", "size")
    )

    linked = complexes.merge(coordinate_summary, on="normalized_address", how="left")
    linked = linked.merge(installation_summary, on="normalized_address", how="left")
    linked = linked.merge(inspection_summary, on="normalized_address", how="left")
    linked = linked.merge(corrective_summary, on="normalized_address", how="left")
    count_columns = ["elevator_count", "inspection_count", "inspection_fail_count", "conditional_pass_count", "corrective_count"]
    for column in count_columns:
        linked[column] = linked[column].fillna(0).astype(int)
    linked["linked_at"] = datetime.now(UTC).isoformat()

    output_dir = ROOT / "data" / "processed" / "complex_linkage"
    output_dir.mkdir(parents=True, exist_ok=True)
    linked.to_parquet(output_dir / "complex_linkage.parquet", index=False)

    cursor = connection.cursor()
    cursor.execute("""
        create table if not exists complex_data_links (
            complex_id text primary key references complexes(complex_id), normalized_address text not null,
            latitude real, longitude real, elevator_count integer not null, inspection_count integer not null,
            inspection_fail_count integer not null, conditional_pass_count integer not null,
            corrective_count integer not null, last_inspection_date text, linked_at timestamp not null
        )
    """)
    cursor.execute("create index if not exists ix_complex_data_links_normalized_address on complex_data_links(normalized_address)")
    cursor.execute("delete from complex_data_links")
    columns = ["complex_id","normalized_address","latitude","longitude",*count_columns,"last_inspection_date","linked_at"]
    cursor.executemany(
        f"insert into complex_data_links ({','.join(columns)}) values ({','.join('?' for _ in columns)})",
        linked[columns].where(pd.notna(linked[columns]), None).itertuples(index=False, name=None),
    )
    coordinate_rows = linked.dropna(subset=["latitude", "longitude"])
    cursor.executemany(
        "update complexes set latitude=?, longitude=? where complex_id=?",
        coordinate_rows[["latitude", "longitude", "complex_id"]].itertuples(index=False, name=None),
    )
    connection.commit(); connection.close()
    print({
        "complexes": len(linked),
        "coordinate_links": int(linked["latitude"].notna().sum()),
        "elevator_links": int((linked["elevator_count"] > 0).sum()),
        "inspection_links": int((linked["inspection_count"] > 0).sum()),
        "corrective_links": int((linked["corrective_count"] > 0).sum()),
    })


if __name__ == "__main__":
    main()
