from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    classification_report,
    roc_auc_score,
)

FLOOD_FEATURES = [
    "elevation_m",
    "slope_degree",
    "rain_1h_mm",
    "rain_3h_mm",
    "rain_24h_mm",
    "antecedent_rain_3d_mm",
    "sewer_level_ratio",
    "distance_to_stream_m",
    "impervious_ratio",
    "flood_history_count_500m",
    "basement_parking",
    "households",
    "building_age_years",
]

FACILITY_FEATURES = [
    "equipment_age_years",
    "inspection_fail_count_3y",
    "conditional_pass_count_3y",
    "corrective_recommendation_count_3y",
    "months_since_last_inspection",
    "maintenance_cost_per_unit",
    "maintenance_cost_change_12m",
    "repair_cost_change_12m",
    "households_per_equipment",
    "building_age_years",
    "humidity_mean_7d",
    "heavy_rain_days_30d",
]


def temporal_split(df: pd.DataFrame, date_column: str, test_ratio: float = 0.2):
    ordered = df.sort_values(date_column).reset_index(drop=True)
    split_index = int(len(ordered) * (1 - test_ratio))
    return ordered.iloc[:split_index], ordered.iloc[split_index:]


def train_binary_model(
    df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
    date_column: str,
    output_path: Path,
) -> None:
    required = set(feature_columns + [target_column, date_column])
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {missing}")

    clean = df.dropna(subset=feature_columns + [target_column, date_column]).copy()
    if clean[target_column].nunique() < 2:
        raise ValueError(f"{target_column}에 0과 1 두 클래스가 모두 필요합니다.")

    train_df, test_df = temporal_split(clean, date_column)
    X_train = train_df[feature_columns]
    y_train = train_df[target_column].astype(int)
    X_test = test_df[feature_columns]
    y_test = test_df[target_column].astype(int)

    model = HistGradientBoostingClassifier(
        learning_rate=0.06,
        max_iter=250,
        max_leaf_nodes=31,
        l2_regularization=1.0,
        random_state=42,
    )
    model.fit(X_train, y_train)

    probabilities = model.predict_proba(X_test)[:, 1]
    predictions = (probabilities >= 0.5).astype(int)

    print(f"\n[{target_column}]")
    print(classification_report(y_test, predictions, digits=4))
    print("ROC-AUC:", round(roc_auc_score(y_test, probabilities), 4))
    metrics = {
        "roc_auc": round(roc_auc_score(y_test, probabilities), 4),
        "pr_auc": round(average_precision_score(y_test, probabilities), 4),
        "brier_score": round(brier_score_loss(y_test, probabilities), 4),
    }
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "features": feature_columns,
            "target": target_column,
            "date_column": date_column,
            "model_version": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
            "metrics": metrics,
            "validated": False,
            "validation_note": "지역 외부검증과 최근 연도 holdout 승인 전 운영 배포 금지",
        },
        output_path,
    )
    print("저장:", output_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="data/modeling_table.csv",
        help="침수·설비 학습용 통합 테이블",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts",
        help="학습 모델 저장 폴더",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(
            f"{input_path}가 없습니다. README의 모델링 테이블 컬럼을 먼저 구성하세요."
        )

    df = pd.read_csv(input_path)
    df["observation_time"] = pd.to_datetime(df["observation_time"])
    df["reference_date"] = pd.to_datetime(df["reference_date"])

    output_dir = Path(args.output_dir)

    train_binary_model(
        df=df,
        feature_columns=FLOOD_FEATURES,
        target_column="flood_within_6h",
        date_column="observation_time",
        output_path=output_dir / "flood_model.joblib",
    )

    train_binary_model(
        df=df,
        feature_columns=FACILITY_FEATURES,
        target_column="facility_issue_within_30d",
        date_column="reference_date",
        output_path=output_dir / "facility_model.joblib",
    )


if __name__ == "__main__":
    main()
