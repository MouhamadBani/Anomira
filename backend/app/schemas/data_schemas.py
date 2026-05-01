from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DatasetReference(BaseModel):
    dataset_id: str = Field(..., description="Dataset identifier from /api/upload")


class UploadResponse(BaseModel):
    dataset_id: str
    filename: str
    row_count: int
    column_count: int
    columns: List[str]
    preview: List[Dict[str, Any]]


class UploadCapabilitiesResponse(BaseModel):
    max_upload_size_mb: Optional[int]
    max_upload_size_bytes: Optional[int]
    max_cloud_download_size_mb: Optional[int]
    max_cloud_download_size_bytes: Optional[int]
    local_upload_unlimited: bool
    cloud_download_unlimited: bool
    supported_formats: List[str]
    supported_cloud_url_protocols: List[str]
    cloud_url_upload_enabled: bool
    large_dataset_threshold_rows: int
    tb_ready_async_job_enabled: bool = False
    chunked_tb_mode_formats: List[str] = Field(default_factory=list)
    tb_mode_trigger_mb: Optional[int] = None
    notes: str


class UploadUrlRequest(BaseModel):
    url: str = Field(..., description="HTTP/HTTPS cloud URL to dataset file")
    filename: Optional[str] = Field(default=None, description="Optional filename override including extension")


class ProfileRequest(DatasetReference):
    pass


class AnomalyRequest(DatasetReference):
    top_n: Optional[int] = Field(default=100, ge=1, le=1000)
    expected_columns: Optional[List[str]] = None


class AnalyzeRequest(DatasetReference):
    top_n: Optional[int] = Field(default=100, ge=1, le=1000)
    expected_columns: Optional[List[str]] = None


class ReportRequest(DatasetReference):
    top_n: Optional[int] = Field(default=100, ge=1, le=1000)
    expected_columns: Optional[List[str]] = None


class ProfileResponse(BaseModel):
    dataset_id: str
    row_count: int
    column_count: int
    column_types: Dict[str, str]
    missing_values: Dict[str, Dict[str, float]]
    duplicate_rows: int
    constant_columns: List[str]
    high_cardinality_columns: List[str]
    invalid_dates: Dict[str, int]
    skewed_numeric_columns: Dict[str, float]
    outlier_counts: Dict[str, int]
    type_mismatch_counts: Dict[str, int]
    geospatial_summary: Dict[str, Any] = Field(default_factory=dict)
    column_health: List[Dict[str, Any]]


class AnomalyRecord(BaseModel):
    row_index: int
    anomaly_score: float
    severity: str
    anomaly_types: List[str]
    anomaly_categories: List[str] = Field(default_factory=list)
    primary_category: Optional[str] = None
    explanation: str
    affected_columns: List[str]
    recommended_action: str
    record: Dict[str, Any]


class AnomalyResponse(BaseModel):
    dataset_id: str
    total_rows: int
    suspicious_count: int
    severity_breakdown: Dict[str, int]
    anomaly_type_breakdown: Dict[str, int]
    anomaly_category_breakdown: Dict[str, int] = Field(default_factory=dict)
    anomaly_groups: List[Dict[str, Any]] = Field(default_factory=list)
    quality_anomalies: Dict[str, Any]
    time_series_events: List[Dict[str, Any]]
    collective_anomaly_segments: List[Dict[str, Any]]
    anomaly_score_distribution: List[Dict[str, Any]]
    records: List[AnomalyRecord]
    recommendations: List[str]
    auto_fix_plan: List[Dict[str, Any]]
    analysis_metadata: Dict[str, Any] = Field(default_factory=dict)


class AnalyzeResponse(BaseModel):
    dataset_id: str
    profile: ProfileResponse
    anomalies: AnomalyResponse


class AsyncAnalyzeUrlRequest(BaseModel):
    url: str = Field(..., description="HTTP/HTTPS cloud URL to dataset file")
    filename: Optional[str] = Field(default=None, description="Optional filename override including extension")
    top_n: Optional[int] = Field(default=100, ge=1, le=1000)
    expected_columns: Optional[List[str]] = None


class JobCreatedResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    stage: str
    progress: float
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    stage: str
    progress: float
    message: str
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    dataset: Optional[UploadResponse] = None
    analysis: Optional[AnalyzeResponse] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
