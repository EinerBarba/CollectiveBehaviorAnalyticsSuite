import uuid
from datetime import datetime
from pydantic import BaseModel
from app.schemas._enums import MetricValueType, MetricScope


class MetricDefinitionOut(BaseModel):
    key: str
    display_name: str
    unit: str | None
    value_type: MetricValueType
    scope: MetricScope

    class Config:
        from_attributes = True


class MetricResultCreate(BaseModel):
    dataset_version_id: uuid.UUID
    processing_run_id: uuid.UUID
    metric_key: str
    experiment_subject_id: uuid.UUID | None = None
    subject_group_id: uuid.UUID | None = None
    experiment_phase_id: uuid.UUID | None = None
    value_numeric: float | None = None
    value_json: dict | None = None


class MetricResultOut(BaseModel):
    id: uuid.UUID
    dataset_version_id: uuid.UUID
    processing_run_id: uuid.UUID
    metric_key: str
    experiment_subject_id: uuid.UUID | None
    subject_group_id: uuid.UUID | None
    experiment_phase_id: uuid.UUID | None
    value_numeric: float | None
    value_json: dict | None
    computed_at: datetime

    class Config:
        from_attributes = True


class ComparisonRunCreate(BaseModel):
    experiment_id: uuid.UUID
    reference_dataset_version_id: uuid.UUID
    candidate_dataset_version_id: uuid.UUID
    processing_run_id: uuid.UUID


class ComparisonRunOut(BaseModel):
    id: uuid.UUID
    experiment_id: uuid.UUID
    reference_dataset_version_id: uuid.UUID
    candidate_dataset_version_id: uuid.UUID
    processing_run_id: uuid.UUID
    created_by: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True


class ComparisonResultCreate(BaseModel):
    comparison_run_id: uuid.UUID
    experiment_subject_id: uuid.UUID | None = None
    metric_name: str
    value_numeric: float
    frame_range_start: int | None = None
    frame_range_end: int | None = None
    extra: dict | None = None


class ComparisonResultOut(BaseModel):
    id: uuid.UUID
    comparison_run_id: uuid.UUID
    experiment_subject_id: uuid.UUID | None
    metric_name: str
    value_numeric: float
    frame_range_start: int | None
    frame_range_end: int | None
    extra: dict | None

    class Config:
        from_attributes = True
