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


class ResilienceReportSnapshot(Base):
    __tablename__ = "resilience_report_snapshots"
    report_id: Mapped[str] = mapped_column(ForeignKey("report_artifacts.report_id"), primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(20), index=True)
    scope_value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    report_version: Mapped[str] = mapped_column(String(40), default="resilience-report-v1")
    payload_snapshot: Mapped[dict] = mapped_column(JSON)
    reference_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pdf_path: Mapped[str | None] = mapped_column(Text)
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


class CascadeAnalysisRun(Base):
    __tablename__ = "cascade_analysis_runs"
    run_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    complex_id: Mapped[str] = mapped_column(ForeignKey("complexes.complex_id"), index=True)
    analysis_mode: Mapped[str] = mapped_column(String(20), index=True)
    scenario_run_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    cascade_level: Mapped[int] = mapped_column(Integer)
    active_path_count: Mapped[int] = mapped_column(Integer)
    data_confidence: Mapped[str] = mapped_column(String(20))
    method_type: Mapped[str] = mapped_column(String(40), default="evidence_graph")
    method_version: Mapped[str] = mapped_column(String(40), default="cascade-v1")
    input_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    result_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CascadePath(Base):
    __tablename__ = "cascade_paths"
    path_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("cascade_analysis_runs.run_id"), index=True)
    path_name: Mapped[str] = mapped_column(String(200))
    nodes: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30))
    severity: Mapped[str] = mapped_column(String(20))
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    missing_evidence: Mapped[list] = mapped_column(JSON, default=list)
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


class HistoricalFloodFeature(Base):
    __tablename__ = "historical_flood_features"
    historical_flood_feature_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    complex_id: Mapped[str] = mapped_column(ForeignKey("complexes.complex_id"), unique=True, index=True)
    nearest_trace_distance_m: Mapped[float | None] = mapped_column(Float)
    intersects_trace: Mapped[bool] = mapped_column(Boolean, default=False)
    overlap_ratio_100m: Mapped[float] = mapped_column(Float, default=0)
    overlap_ratio_300m: Mapped[float] = mapped_column(Float, default=0)
    overlap_ratio_500m: Mapped[float] = mapped_column(Float, default=0)
    hit_years_point: Mapped[list] = mapped_column(JSON, default=list)
    hit_years_100m: Mapped[list] = mapped_column(JSON, default=list)
    hit_years_300m: Mapped[list] = mapped_column(JSON, default=list)
    hit_years_500m: Mapped[list] = mapped_column(JSON, default=list)
    source_years: Mapped[list] = mapped_column(JSON, default=list)
    missing_years: Mapped[list] = mapped_column(JSON, default=list)
    source_feature_count: Mapped[int] = mapped_column(Integer)
    data_version: Mapped[str] = mapped_column(String(100))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data_quality_status: Mapped[str] = mapped_column(String(40), index=True)


class RainPumpProximityFeature(Base):
    __tablename__ = "rain_pump_proximity_features"
    rain_pump_proximity_feature_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    complex_id: Mapped[str] = mapped_column(ForeignKey("complexes.complex_id"), unique=True, index=True)
    nearest_pump_id: Mapped[str | None] = mapped_column(String(100))
    nearest_pump_name: Mapped[str | None] = mapped_column(String(200))
    nearest_pump_distance_m: Mapped[float | None] = mapped_column(Float)
    pump_count_1km: Mapped[int] = mapped_column(Integer, default=0)
    pump_count_3km: Mapped[int] = mapped_column(Integer, default=0)
    pump_count_5km: Mapped[int] = mapped_column(Integer, default=0)
    source_feature_count: Mapped[int] = mapped_column(Integer)
    capacity_status: Mapped[str] = mapped_column(String(40))
    operation_status: Mapped[str] = mapped_column(String(40))
    data_version: Mapped[str] = mapped_column(String(100))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data_quality_status: Mapped[str] = mapped_column(String(40), index=True)


class RainfallHistoricalStatistic(Base):
    __tablename__ = "rainfall_historical_statistics"
    rainfall_historical_statistic_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    station_id: Mapped[str] = mapped_column(String(100), index=True)
    station_name: Mapped[str] = mapped_column(String(200), index=True)
    source_year: Mapped[int] = mapped_column(Integer, index=True)
    observed_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    record_count: Mapped[int] = mapped_column(Integer)
    duplicate_count: Mapped[int] = mapped_column(Integer)
    invalid_count: Mapped[int] = mapped_column(Integer)
    completeness_ratio: Mapped[float] = mapped_column(Float)
    rainfall_total_mm: Mapped[float] = mapped_column(Float)
    max_10m_mm: Mapped[float] = mapped_column(Float)
    max_1h_mm: Mapped[float | None] = mapped_column(Float)
    max_3h_mm: Mapped[float | None] = mapped_column(Float)
    max_24h_mm: Mapped[float | None] = mapped_column(Float)
    data_version: Mapped[str] = mapped_column(String(100))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data_quality_status: Mapped[str] = mapped_column(String(40), index=True)


class FloodSpatialFeature(Base):
    """Operational, compact Seoul hydrology feature snapshot per LH complex.

    Large geometries and observations remain in GeoParquet/Parquet.  This table
    only stores values required by the API and dashboard.
    """

    __tablename__ = "flood_spatial_features"
    complex_id: Mapped[str] = mapped_column(ForeignKey("complexes.complex_id"), primary_key=True)
    historical_flood_overlap: Mapped[bool | None] = mapped_column(Boolean)
    historical_flood_count_100m: Mapped[int | None] = mapped_column(Integer)
    historical_flood_count_300m: Mapped[int | None] = mapped_column(Integer)
    historical_flood_count_500m: Mapped[int | None] = mapped_column(Integer)
    historical_flood_area_ratio_100m: Mapped[float | None] = mapped_column(Float)
    historical_flood_area_ratio_300m: Mapped[float | None] = mapped_column(Float)
    historical_flood_area_ratio_500m: Mapped[float | None] = mapped_column(Float)
    last_flood_year: Mapped[int | None] = mapped_column(Integer)
    expected_flood_overlap: Mapped[bool | None] = mapped_column(Boolean)
    expected_flood_area_ratio_100m: Mapped[float | None] = mapped_column(Float)
    expected_flood_area_ratio_300m: Mapped[float | None] = mapped_column(Float)
    expected_flood_area_ratio_500m: Mapped[float | None] = mapped_column(Float)
    expected_flood_max_stage: Mapped[float | None] = mapped_column(Float)
    distance_to_nearest_pump_station_m: Mapped[float | None] = mapped_column(Float)
    pump_station_count_500m: Mapped[int | None] = mapped_column(Integer)
    pump_station_count_1km: Mapped[int | None] = mapped_column(Integer)
    pump_station_count_2km: Mapped[int | None] = mapped_column(Integer)
    nearby_total_pump_capacity_1km: Mapped[float | None] = mapped_column(Float)
    nearest_rain_station_id: Mapped[str | None] = mapped_column(String(100))
    rain_station_distance_m: Mapped[float | None] = mapped_column(Float)
    nearest_river_station_id: Mapped[str | None] = mapped_column(String(100))
    river_station_distance_m: Mapped[float | None] = mapped_column(Float)
    dataset_statuses: Mapped[dict] = mapped_column(JSON, default=dict)
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    data_version: Mapped[str] = mapped_column(String(100))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data_quality_status: Mapped[str] = mapped_column(String(40), index=True)
