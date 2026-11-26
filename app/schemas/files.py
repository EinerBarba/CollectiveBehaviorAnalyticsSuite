import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas._enums import FileType


class FileCreate(BaseModel):
    experiment_id: uuid.UUID | None = None
    file_type: FileType
    logical_name: str = Field(min_length=1, max_length=500)
    description: str | None = None
    is_raw: bool = False


class FileUpdate(BaseModel):
    logical_name: str | None = None
    description: str | None = None


class FileOut(BaseModel):
    id: uuid.UUID
    experiment_id: uuid.UUID | None
    file_type: FileType
    logical_name: str
    description: str | None
    is_raw: bool
    current_version_id: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True


class FileVersionCreate(BaseModel):
    file_id: uuid.UUID
    version_number: int
    storage_bucket: str
    storage_key: str
    mime_type: str | None = None
    size_bytes: int
    checksum_sha256: str
    is_current: bool = True


class FileVersionOut(BaseModel):
    id: uuid.UUID
    file_id: uuid.UUID
    version_number: int
    storage_bucket: str
    storage_key: str
    mime_type: str | None
    size_bytes: int
    checksum_sha256: str
    uploaded_by: uuid.UUID
    uploaded_at: datetime
    is_current: bool

    class Config:
        from_attributes = True
