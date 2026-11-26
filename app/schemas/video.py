import uuid
from datetime import datetime

from pydantic import BaseModel


class FileVersionOut(BaseModel):
    id: uuid.UUID
    file_id: uuid.UUID
    version_number: int
    logical_name: str
    storage_key: str
    mime_type: str | None
    size_bytes: int
    checksum_sha256: str
    uploaded_at: datetime


class FrameExtractionOut(BaseModel):
    run_id: uuid.UUID
    dataset_version_id: uuid.UUID
    manifest_file_version_id: uuid.UUID
    requested_fps: float
    effective_fps: float
    frame_count: int
    source_width: int
    source_height: int
    source_fps: float
    source_frame_count: int


class VideoUploadOut(BaseModel):
    file_version: FileVersionOut


class VideoMetadataOut(BaseModel):
    fps: float
    frame_count: int
    width: int
    height: int
    duration_seconds: float