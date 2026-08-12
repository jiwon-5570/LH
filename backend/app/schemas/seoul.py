from datetime import datetime

from pydantic import BaseModel, Field


class AssessmentOut(BaseModel):
    assessment_id: str
    assessment_type: str
    score: float | None
    grade: str
    method_type: str
    method_version: str
    features: dict
    explanation: dict
    data_quality_status: str
    assessed_at: datetime


class SeoulComplexSummary(BaseModel):
    complex_id: str
    complex_name: str
    address: str
    latitude: float | None
    longitude: float | None
    district: str | None
    analysis_eligible: bool
    validation_status: str
    resilience_score: float | None = None
    resilience_grade: str | None = None
    data_confidence: float | None = None
    assessed_at: datetime | None = None


class StressTestRequest(BaseModel):
    complex_id: str
    rain_change_pct: float = Field(ge=0, le=100)
    sewer_change_pct: float = Field(ge=0, le=100)


class StressTestOut(BaseModel):
    run_id: str
    complex_id: str
    scenario_type: str
    base_features: dict
    modified_features: dict
    base_score: float | None
    scenario_score: float | None
    method_version: str
    data_quality_status: str
    created_at: datetime
