from datetime import date, datetime
from typing import Literal

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


class ScenarioRunRequest(BaseModel):
    scenario_name: str | None = Field(default=None, max_length=120)
    rain_change_pct: float = Field(default=0, ge=-50, le=200, allow_inf_nan=False)
    sewer_change_pct: float = Field(default=0, ge=-50, le=100, allow_inf_nan=False)
    river_change_pct: float = Field(default=0, ge=-50, le=100, allow_inf_nan=False)
    rain_1h_mm: float | None = Field(default=None, ge=0, le=500, allow_inf_nan=False)
    rain_3h_mm: float | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    rain_6h_mm: float | None = Field(default=None, ge=0, le=1500, allow_inf_nan=False)
    rain_24h_mm: float | None = Field(default=None, ge=0, le=2500, allow_inf_nan=False)
    target_complex_id: str | None = None
    apply_to_all_complexes: bool = True
    created_by: str = Field(default="dashboard-user", max_length=100)


class ScenarioSummary(BaseModel):
    total: int
    complete: int
    insufficient: int
    vulnerable: int
    caution: int
    average_resilience_score: float | None


class ScenarioComplexResult(BaseModel):
    complex_id: str
    complex_name: str
    latitude: float | None
    longitude: float | None
    base_resilience_score: float | None = None
    scenario_resilience_score: float | None
    resilience_delta: float | None = None
    base_climate_vulnerability: float | None = None
    scenario_climate_vulnerability: float | None = None
    climate_delta: float | None = None
    base_dynamic_stress: float | None = None
    scenario_dynamic_stress: float | None = None
    base_grade: str | None = None
    scenario_grade: str | None = None
    top_changed_factors: list[dict] = []
    data_confidence: float | None
    base_features: dict = {}
    scenario_features: dict = {}
    error: str | None = None


class ScenarioRunResponse(BaseModel):
    scenario_id: str
    scenario_name: str
    created_at: datetime
    method_type: str
    method_version: str
    scenario_input: bool
    source: str
    base_summary: ScenarioSummary
    scenario_summary: ScenarioSummary
    complex_results: list[ScenarioComplexResult]


class ResilienceReportRequest(BaseModel):
    report_type: Literal["resilience", "climate", "facility", "cascade"] = "resilience"
    scope_type: Literal["seoul", "district", "complex"] = "seoul"
    scope_value: str | None = None
    reference_date: date | None = None


class ResilienceReportResponse(BaseModel):
    report_id: str
    report_type: str
    report_type_label: str
    scope_type: str
    scope: dict
    generated_at: datetime | str
    reference_time: datetime | str | None
    reference_date: str | None
    freshness: str
    summary: dict
    comparison: dict
    distribution: dict
    ranking: list[dict]
    findings: list[dict]
    recommendations: list[dict]
    cascade: dict
    top_factors: list[dict]
    detail: dict
    methodology: dict
    data_sources: list[dict]
    limitations: list[str]
    report_version: str
    ai_explanation: str
    html_download_url: str
    pdf_download_url: str
