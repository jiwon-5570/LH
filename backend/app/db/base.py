from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass

class Complex(Base):
    __tablename__ = "complexes"
    complex_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    complex_name: Mapped[str] = mapped_column(String(300))
    address: Mapped[str] = mapped_column(String(500))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    source_name: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(Text)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_version: Mapped[str] = mapped_column(String(100))
    validation_status: Mapped[str] = mapped_column(String(40))
    collection_run_id: Mapped[str] = mapped_column(String(100))

class ComplexDataLink(Base):
    __tablename__ = "complex_data_links"
    complex_id: Mapped[str] = mapped_column(ForeignKey("complexes.complex_id"), primary_key=True)
    normalized_address: Mapped[str] = mapped_column(String(500), index=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    elevator_count: Mapped[int] = mapped_column(Integer, default=0)
    inspection_count: Mapped[int] = mapped_column(Integer, default=0)
    inspection_fail_count: Mapped[int] = mapped_column(Integer, default=0)
    conditional_pass_count: Mapped[int] = mapped_column(Integer, default=0)
    corrective_count: Mapped[int] = mapped_column(Integer, default=0)
    last_inspection_date: Mapped[str | None] = mapped_column(String(30))
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class Prediction(Base):
    __tablename__ = "predictions"
    prediction_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    complex_id: Mapped[str] = mapped_column(ForeignKey("complexes.complex_id"), index=True)
    risk_type: Mapped[str] = mapped_column(String(30))
    model_version: Mapped[str] = mapped_column(String(100))
    prediction_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    target_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    risk_probability: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(30))
    feature_snapshot: Mapped[dict] = mapped_column(JSON)
    data_quality_status: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class Alert(Base):
    __tablename__ = "alerts"
    alert_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    complex_id: Mapped[str] = mapped_column(ForeignKey("complexes.complex_id"))
    risk_type: Mapped[str] = mapped_column(String(30))
    risk_level: Mapped[str] = mapped_column(String(30))
    summary: Mapped[str] = mapped_column(Text)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class DataCollectionRun(Base):
    __tablename__ = "data_collection_runs"
    collection_run_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(100), index=True)
    source_name: Mapped[str] = mapped_column(String(300))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30))
    raw_path: Mapped[str | None] = mapped_column(Text)
    processed_path: Mapped[str | None] = mapped_column(Text)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    valid_count: Mapped[int] = mapped_column(Integer, default=0)
    quarantined_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    data_version: Mapped[str | None] = mapped_column(String(100))

class DataQualityResult(Base):
    __tablename__ = "data_quality_results"
    quality_result_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    collection_run_id: Mapped[str] = mapped_column(ForeignKey("data_collection_runs.collection_run_id"), index=True)
    dataset_id: Mapped[str] = mapped_column(String(100), index=True)
    check_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30))
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class AIConversation(Base):
    __tablename__ = "ai_conversations"
    conversation_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    complex_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class ReportArtifact(Base):
    __tablename__ = "report_artifacts"
    report_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    report_type: Mapped[str] = mapped_column(String(60))
    complex_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    file_path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class SourceRecord(Base):
    __tablename__ = "source_records"
    source_record_key: Mapped[str] = mapped_column(String(180), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(100), index=True)
    source_record_id: Mapped[str] = mapped_column(String(200), index=True)
    collection_run_id: Mapped[str] = mapped_column(ForeignKey("data_collection_runs.collection_run_id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    data_version: Mapped[str] = mapped_column(String(100))
    validation_status: Mapped[str] = mapped_column(String(30))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SeoulComplexProfile(Base):
    __tablename__ = "seoul_complex_profiles"
    complex_id: Mapped[str] = mapped_column(ForeignKey("complexes.complex_id"), primary_key=True)
    complex_name: Mapped[str] = mapped_column(String(300))
    address: Mapped[str] = mapped_column(String(500))
    normalized_address: Mapped[str] = mapped_column(String(500), index=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    district: Mapped[str | None] = mapped_column(String(80))
    household_count: Mapped[int | None] = mapped_column(Integer)
    building_count: Mapped[int | None] = mapped_column(Integer)
    completion_date: Mapped[str | None] = mapped_column(String(30))
    building_age_years: Mapped[float | None] = mapped_column(Float)
    kapt_code: Mapped[str | None] = mapped_column(String(40), index=True)
    analysis_eligible: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    eligibility_reason: Mapped[str] = mapped_column(String(200))
    validation_status: Mapped[str] = mapped_column(String(40), index=True)
    source_name: Mapped[str] = mapped_column(String(300))
    data_version: Mapped[str] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"
    assessment_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    complex_id: Mapped[str] = mapped_column(ForeignKey("complexes.complex_id"), index=True)
    assessment_type: Mapped[str] = mapped_column(String(60), index=True)
    score: Mapped[float | None] = mapped_column(Float)
    grade: Mapped[str] = mapped_column(String(40))
    method_type: Mapped[str] = mapped_column(String(40))
    method_version: Mapped[str] = mapped_column(String(100), index=True)
    feature_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    explanation_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    data_quality_status: Mapped[str] = mapped_column(String(40), index=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StressTestRun(Base):
    __tablename__ = "stress_test_runs"
    run_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    complex_id: Mapped[str] = mapped_column(ForeignKey("complexes.complex_id"), index=True)
    scenario_type: Mapped[str] = mapped_column(String(80))
    base_features: Mapped[dict] = mapped_column(JSON)
    modified_features: Mapped[dict] = mapped_column(JSON)
    base_score: Mapped[float | None] = mapped_column(Float)
    scenario_score: Mapped[float | None] = mapped_column(Float)
    method_version: Mapped[str] = mapped_column(String(100))
    data_quality_status: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ModelVersion(Base):
    __tablename__ = "model_versions"
    model_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    model_name: Mapped[str] = mapped_column(String(200))
    model_type: Mapped[str] = mapped_column(String(60))
    version: Mapped[str] = mapped_column(String(100))
    target_name: Mapped[str] = mapped_column(String(100))
    training_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    training_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    training_data_version: Mapped[str | None] = mapped_column(String(100))
    feature_list: Mapped[list] = mapped_column(JSON, default=list)
    artifact_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), index=True)
    status_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ModelEvaluation(Base):
    __tablename__ = "model_evaluations"
    evaluation_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("model_versions.model_id"), index=True)
    roc_auc: Mapped[float | None] = mapped_column(Float)
    pr_auc: Mapped[float | None] = mapped_column(Float)
    precision: Mapped[float | None] = mapped_column(Float)
    recall: Mapped[float | None] = mapped_column(Float)
    f1: Mapped[float | None] = mapped_column(Float)
    brier: Mapped[float | None] = mapped_column(Float)
    split_strategy: Mapped[str] = mapped_column(String(100))
    evaluation_details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TerrainFeature(Base):
    __tablename__ = "terrain_features"
    terrain_feature_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    complex_id: Mapped[str] = mapped_column(ForeignKey("complexes.complex_id"), unique=True, index=True)
    elevation_m: Mapped[float | None] = mapped_column(Float)
    min_elevation_100m: Mapped[float | None] = mapped_column(Float)
    mean_elevation_100m: Mapped[float | None] = mapped_column(Float)
    relative_elevation_100m: Mapped[float | None] = mapped_column(Float)
    min_elevation_300m: Mapped[float | None] = mapped_column(Float)
    mean_elevation_300m: Mapped[float | None] = mapped_column(Float)
    relative_elevation_300m: Mapped[float | None] = mapped_column(Float)
    min_elevation_500m: Mapped[float | None] = mapped_column(Float)
    mean_elevation_500m: Mapped[float | None] = mapped_column(Float)
    relative_elevation_500m: Mapped[float | None] = mapped_column(Float)
    slope_mean_100m: Mapped[float | None] = mapped_column(Float)
    slope_mean_300m: Mapped[float | None] = mapped_column(Float)
    slope_mean_500m: Mapped[float | None] = mapped_column(Float)
    slope_max_100m: Mapped[float | None] = mapped_column(Float)
    slope_max_300m: Mapped[float | None] = mapped_column(Float)
    slope_max_500m: Mapped[float | None] = mapped_column(Float)
    lowland_index_100m: Mapped[float | None] = mapped_column(Float)
    lowland_index_300m: Mapped[float | None] = mapped_column(Float)
    lowland_index_500m: Mapped[float | None] = mapped_column(Float)
    dem_coverage_ratio_100m: Mapped[float] = mapped_column(Float, default=0)
    dem_coverage_ratio_300m: Mapped[float] = mapped_column(Float, default=0)
    dem_coverage_ratio_500m: Mapped[float] = mapped_column(Float, default=0)
    data_version: Mapped[str] = mapped_column(String(100))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data_quality_status: Mapped[str] = mapped_column(String(40), index=True)
