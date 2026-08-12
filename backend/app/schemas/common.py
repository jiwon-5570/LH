from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ComplexOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    complex_id: str
    complex_name: str
    address: str
    latitude: float | None
    longitude: float | None
    source_name: str
    source_url: str | None
    collected_at: datetime
    observed_at: datetime | None
    data_version: str
    validation_status: str

class PredictionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    prediction_id: str
    complex_id: str
    risk_type: str
    model_version: str
    prediction_time: datetime
    target_time: datetime | None
    risk_probability: float = Field(ge=0, le=1)
    risk_level: str
    feature_snapshot: dict
    data_quality_status: str

class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    alert_id: str
    complex_id: str
    risk_type: str
    risk_level: str
    summary: str
    acknowledged: bool
    created_at: datetime

