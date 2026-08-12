from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./lh_predict.db"
    frontend_api_url: str = "http://localhost:8000"
    naver_map_client_id: str = ""
    naver_map_client_secret: str = ""
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5"
    data_go_kr_service_key: str = ""
    kma_service_key: str = ""
    seoul_rainfall_api_key: str = ""
    seoul_sewer_level_api_key: str = ""
    seoul_flood_forecast_map_api_key: str = ""
    raw_data_dir: Path = Path("data/raw")
    staging_data_dir: Path = Path("data/staging")
    processed_data_dir: Path = Path("data/processed")
    quarantine_data_dir: Path = Path("data/quarantine")
    archive_data_dir: Path = Path("data/archive")
    source_record_sample_limit: int = 100
    report_output_dir: Path = Path("artifacts/reports")
    model_output_dir: Path = Path("artifacts/models")
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()
