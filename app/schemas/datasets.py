import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas._enums import DatasetOrigin, DatasetStatus


class DatasetTypeOut(BaseModel):
    key: str
    display_name: str

    class Config:
        from_attributes = True


class DatasetCreate(BaseModel):
    experiment_id: uuid.UUID
    dataset_type: str
    name: str = Field(min_length=1, max_length=300)
    description: str | None = None
    origin: DatasetOrigin
    is_ground_truth: bool = False
    status: DatasetStatus = "draft"


class DatasetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: DatasetStatus | None = None
    is_ground_truth: bool | None = None


class DatasetOut(BaseModel):
    id: uuid.UUID
    experiment_id: uuid.UUID
    dataset_type: str
    name: str
    description: str | None
    origin: DatasetOrigin
    is_ground_truth: bool
    status: DatasetStatus
    current_version_id: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True


class DatasetVersionCreate(BaseModel):
    dataset_id: uuid.UUID
    version_number: int
    schema_version: str | None = None
    changelog: str | None = None
    is_current: bool = True


class DatasetVersionOut(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    version_number: int
    schema_version: str | None
    changelog: str | None
    created_by: uuid.UUID
    created_at: datetime
    is_current: bool

    class Config:
        from_attributes = True


class DatasetSpatialMetadataUpsert(BaseModel):
    dataset_version_id: uuid.UUID
    coordinate_system: str | None = None
    sampling_rate_hz: float | None = None
    units: str | None = None
    frame_start: int | None = None
    frame_end: int | None = None


class DatasetSpatialMetadataOut(BaseModel):
    dataset_version_id: uuid.UUID
    coordinate_system: str | None
    sampling_rate_hz: float | None
    units: str | None
    frame_start: int | None
    frame_end: int | None

    class Config:
        from_attributes = True


class DatasetFileCreate(BaseModel):
    dataset_version_id: uuid.UUID
    file_version_id: uuid.UUID
    role: str = "primary"


class DatasetFileOut(BaseModel):
    dataset_version_id: uuid.UUID
    file_version_id: uuid.UUID
    role: str

    class Config:
        from_attributes = True
