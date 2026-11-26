import uuid
from datetime import datetime, date
from pydantic import BaseModel, Field
from app.schemas._enums import ExperimentStatus


class ExperimentCreate(BaseModel):
    laboratory_id: uuid.UUID
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    study_subject_type: str | None = None
    status: ExperimentStatus = "planned"
    start_date: date | None = None
    end_date: date | None = None
    location: str | None = None
    environment_metadata: dict | None = None
    config_metadata: dict | None = None
    notes: str | None = None


class ExperimentUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    study_subject_type: str | None = None
    status: ExperimentStatus | None = None
    start_date: date | None = None
    end_date: date | None = None
    location: str | None = None
    environment_metadata: dict | None = None
    config_metadata: dict | None = None
    notes: str | None = None


class ExperimentOut(BaseModel):
    id: uuid.UUID
    laboratory_id: uuid.UUID
    title: str
    description: str | None
    study_subject_type: str | None
    status: ExperimentStatus
    start_date: date | None
    end_date: date | None
    location: str | None
    environment_metadata: dict | None
    config_metadata: dict | None
    notes: str | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubjectCreate(BaseModel):
    laboratory_id: uuid.UUID
    species: str | None = None
    external_identifier: str | None = None
    label: str = Field(min_length=1, max_length=300)
    metadata_: dict | None = Field(default=None, alias="metadata")

    class Config:
        populate_by_name = True


class SubjectUpdate(BaseModel):
    species: str | None = None
    external_identifier: str | None = None
    label: str | None = None
    metadata_: dict | None = Field(default=None, alias="metadata")

    class Config:
        populate_by_name = True


class SubjectOut(BaseModel):
    id: uuid.UUID
    laboratory_id: uuid.UUID
    species: str | None
    external_identifier: str | None
    label: str
    metadata_: dict | None = Field(serialization_alias="metadata")
    created_by: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True


class ExperimentSubjectCreate(BaseModel):
    experiment_id: uuid.UUID
    subject_id: uuid.UUID
    role_in_experiment: str | None = None


class ExperimentSubjectOut(BaseModel):
    id: uuid.UUID
    experiment_id: uuid.UUID
    subject_id: uuid.UUID
    role_in_experiment: str | None
    added_by: uuid.UUID
    added_at: datetime

    class Config:
        from_attributes = True


class SubjectGroupCreate(BaseModel):
    experiment_id: uuid.UUID
    name: str = Field(min_length=1, max_length=300)
    description: str | None = None


class SubjectGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class SubjectGroupOut(BaseModel):
    id: uuid.UUID
    experiment_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class SubjectGroupMemberCreate(BaseModel):
    subject_group_id: uuid.UUID
    experiment_subject_id: uuid.UUID


class SubjectGroupMemberOut(BaseModel):
    subject_group_id: uuid.UUID
    experiment_subject_id: uuid.UUID

    class Config:
        from_attributes = True


class ExperimentPhaseCreate(BaseModel):
    experiment_id: uuid.UUID
    phase_type: str = Field(min_length=1, max_length=200)
    label: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    sequence_order: int | None = None
    notes: str | None = None


class ExperimentPhaseUpdate(BaseModel):
    phase_type: str | None = None
    label: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    sequence_order: int | None = None
    notes: str | None = None


class ExperimentPhaseOut(BaseModel):
    id: uuid.UUID
    experiment_id: uuid.UUID
    phase_type: str
    label: str | None
    start_time: datetime | None
    end_time: datetime | None
    sequence_order: int | None
    notes: str | None

    class Config:
        from_attributes = True
