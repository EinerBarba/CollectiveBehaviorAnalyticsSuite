import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.schemas._enums import RunStatus


class ToolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    category: str
    description: str | None = None


class ToolUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    description: str | None = None


class ToolOut(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    description: str | None

    class Config:
        from_attributes = True


class ToolVersionCreate(BaseModel):
    tool_id: uuid.UUID
    version_label: str
    commit_hash: str | None = None
    container_image: str | None = None
    released_at: datetime | None = None


class ToolVersionUpdate(BaseModel):
    version_label: str | None = None
    commit_hash: str | None = None
    container_image: str | None = None
    released_at: datetime | None = None


class ToolVersionOut(BaseModel):
    id: uuid.UUID
    tool_id: uuid.UUID
    version_label: str
    commit_hash: str | None
    container_image: str | None
    released_at: datetime | None

    class Config:
        from_attributes = True


class MLModelCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    laboratory_id: uuid.UUID
    name: str = Field(min_length=1, max_length=300)
    model_type: str
    description: str | None = None


class MLModelUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    name: str | None = None
    model_type: str | None = None
    description: str | None = None


class MLModelOut(BaseModel):
    id: uuid.UUID
    laboratory_id: uuid.UUID
    name: str
    model_type: str
    description: str | None
    created_by: uuid.UUID
    created_at: datetime

    class Config:
        protected_namespaces = ()
        from_attributes = True


class ModelVersionCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: uuid.UUID
    version_label: str
    hyperparameters: dict | None = None
    artifact_file_version_id: uuid.UUID | None = None
    training_run_id: uuid.UUID | None = None


class ModelVersionUpdate(BaseModel):
    is_deprecated: bool | None = None


class ModelVersionOut(BaseModel):
    id: uuid.UUID
    model_id: uuid.UUID
    version_label: str
    hyperparameters: dict | None
    artifact_file_version_id: uuid.UUID | None
    training_run_id: uuid.UUID | None
    is_deprecated: bool
    created_by: uuid.UUID
    created_at: datetime

    class Config:
        protected_namespaces = ()
        from_attributes = True


class ProcessingRunCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    experiment_id: uuid.UUID
    tool_version_id: uuid.UUID
    model_version_id: uuid.UUID | None = None
    parameters: dict | None = None


class ProcessingRunUpdate(BaseModel):
    status: RunStatus | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    runtime_info: dict | None = None


class ProcessingRunOut(BaseModel):
    id: uuid.UUID
    experiment_id: uuid.UUID
    tool_version_id: uuid.UUID
    model_version_id: uuid.UUID | None
    initiated_by: uuid.UUID
    status: RunStatus
    parameters: dict | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    runtime_info: dict | None
    created_at: datetime

    class Config:
        protected_namespaces = ()
        from_attributes = True


class AccessibleRunOut(BaseModel):
    id: uuid.UUID
    experiment_id: uuid.UUID
    experiment_title: str
    tool_name: str
    status: RunStatus
    created_at: datetime

    class Config:
        from_attributes = False


class ExperimentRunSummary(BaseModel):
    id: uuid.UUID
    tool_name: str
    status: RunStatus
    created_at: datetime
    parameters: dict | None
    runtime_info: dict | None
    error_message: str | None

    class Config:
        from_attributes = False
