import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.schemas._enums import ArtifactType, PredictionType, AssignmentType


class ProcessingRunInputCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    processing_run_id: uuid.UUID
    artifact_type: ArtifactType
    file_version_id: uuid.UUID | None = None
    dataset_version_id: uuid.UUID | None = None
    model_version_id: uuid.UUID | None = None
    role: str


class ProcessingRunInputOut(BaseModel):
    id: uuid.UUID
    processing_run_id: uuid.UUID
    artifact_type: ArtifactType
    file_version_id: uuid.UUID | None
    dataset_version_id: uuid.UUID | None
    model_version_id: uuid.UUID | None
    role: str

    class Config:
        protected_namespaces = ()
        from_attributes = True


class ProcessingRunOutputCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    processing_run_id: uuid.UUID
    artifact_type: ArtifactType
    file_version_id: uuid.UUID | None = None
    dataset_version_id: uuid.UUID | None = None
    model_version_id: uuid.UUID | None = None
    role: str = "primary_output"


class ProcessingRunOutputOut(BaseModel):
    id: uuid.UUID
    processing_run_id: uuid.UUID
    artifact_type: ArtifactType
    file_version_id: uuid.UUID | None
    dataset_version_id: uuid.UUID | None
    model_version_id: uuid.UUID | None
    role: str

    class Config:
        protected_namespaces = ()
        from_attributes = True


class ModelEvaluationCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_version_id: uuid.UUID
    dataset_version_id: uuid.UUID
    processing_run_id: uuid.UUID | None = None
    metric_name: str
    metric_value: float


class ModelEvaluationOut(BaseModel):
    id: uuid.UUID
    model_version_id: uuid.UUID
    dataset_version_id: uuid.UUID
    processing_run_id: uuid.UUID | None
    metric_name: str
    metric_value: float
    computed_at: datetime

    class Config:
        protected_namespaces = ()
        from_attributes = True


class ModelPredictionCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_version_id: uuid.UUID
    processing_run_id: uuid.UUID
    dataset_version_id: uuid.UUID
    experiment_subject_id: uuid.UUID | None = None
    prediction_type: PredictionType
    frame_number: int | None = None
    timestamp_ms: int | None = None
    predicted_label: str | None = None
    confidence: float | None = None
    extra: dict | None = None


class ModelPredictionOut(BaseModel):
    id: uuid.UUID
    model_version_id: uuid.UUID
    processing_run_id: uuid.UUID
    dataset_version_id: uuid.UUID
    experiment_subject_id: uuid.UUID | None
    prediction_type: PredictionType
    frame_number: int | None
    timestamp_ms: int | None
    predicted_label: str | None
    confidence: float | None
    extra: dict | None

    class Config:
        protected_namespaces = ()
        from_attributes = True


class TrackCreate(BaseModel):
    dataset_version_id: uuid.UUID
    processing_run_id: uuid.UUID
    track_label: str
    start_frame: int
    end_frame: int
    confidence_avg: float | None = None


class TrackUpdate(BaseModel):
    track_label: str | None = None
    start_frame: int | None = None
    end_frame: int | None = None
    confidence_avg: float | None = None


class TrackOut(BaseModel):
    id: uuid.UUID
    dataset_version_id: uuid.UUID
    processing_run_id: uuid.UUID
    track_label: str
    start_frame: int
    end_frame: int
    confidence_avg: float | None
    created_at: datetime

    class Config:
        from_attributes = True


class IdentityAssignmentCreate(BaseModel):
    track_id: uuid.UUID
    experiment_subject_id: uuid.UUID
    assignment_type: AssignmentType
    confidence: float | None = None
    assigned_by_run: uuid.UUID | None = None


class IdentityAssignmentOut(BaseModel):
    id: uuid.UUID
    track_id: uuid.UUID
    experiment_subject_id: uuid.UUID
    assignment_type: AssignmentType
    confidence: float | None
    assigned_by_user: uuid.UUID | None
    assigned_by_run: uuid.UUID | None
    assigned_at: datetime
    is_current: bool
    superseded_by: uuid.UUID | None

    class Config:
        from_attributes = True
