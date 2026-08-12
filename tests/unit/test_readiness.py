from pathlib import Path

import joblib

from backend.app.services.readiness import load_validated_model


def test_missing_model_is_not_prediction(tmp_path: Path):
    model, reason = load_validated_model(tmp_path / "missing.joblib")
    assert model is None and "미배포" in reason

def test_unvalidated_model_is_blocked(tmp_path: Path):
    path = tmp_path / "model.joblib"
    joblib.dump({"model":object(),"features":[],"target":"x","date_column":"d","model_version":"v1","metrics":{},"validated":False}, path)
    model, reason = load_validated_model(path)
    assert model is None and reason == "모델 검증 미통과"
