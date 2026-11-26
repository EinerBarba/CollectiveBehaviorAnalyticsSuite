import uuid
from datetime import datetime
from pydantic import BaseModel
from app.schemas._enums import SessionStatus


class ManualAnnotationSessionCreate(BaseModel):
    experiment_id: uuid.UUID
    source_file_version_id: uuid.UUID
    experiment_subject_id: uuid.UUID | None = None


class ManualAnnotationSessionUpdate(BaseModel):
    status: SessionStatus | None = None
    finalized_dataset_version_id: uuid.UUID | None = None


class ManualAnnotationSessionOut(BaseModel):
    id: uuid.UUID
    experiment_id: uuid.UUID
    source_file_version_id: uuid.UUID
    experiment_subject_id: uuid.UUID | None
    status: SessionStatus
    finalized_dataset_version_id: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True


class AnnotationPointCreate(BaseModel):
    session_id: uuid.UUID
    frame_number: int
    timestamp_ms: int | None = None
    x: float
    y: float
    is_estimated: bool = False


class AnnotationPointUpdate(BaseModel):
    x: float | None = None
    y: float | None = None
    is_estimated: bool | None = None


class AnnotationPointOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    frame_number: int
    timestamp_ms: int | None
    x: float
    y: float
    is_estimated: bool
    created_by: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True
