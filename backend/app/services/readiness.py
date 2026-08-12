from pathlib import Path

import joblib

REQUIRED_MODEL_FIELDS = {"model", "features", "target", "date_column", "model_version", "metrics", "validated"}

def load_validated_model(path: Path):
    if not path.exists():
        return None, "학습 데이터 부족 또는 모델 미배포"
    artifact = joblib.load(path)
    missing = REQUIRED_MODEL_FIELDS - set(artifact)
    if missing:
        return None, f"모델 메타데이터 누락: {', '.join(sorted(missing))}"
    if artifact["validated"] is not True:
        return None, "모델 검증 미통과"
    return artifact, None

