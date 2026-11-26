import uuid
from datetime import datetime
from pydantic import BaseModel


class StimulusTypeOut(BaseModel):
    key: str
    display_name: str

    class Config:
        from_attributes = True


class StimulusCreate(BaseModel):
    experiment_id: uuid.UUID
    stimulus_type: str
    description: str | None = None
    configuration: dict | None = None


class StimulusUpdate(BaseModel):
    description: str | None = None
    configuration: dict | None = None


class StimulusOut(BaseModel):
    id: uuid.UUID
    experiment_id: uuid.UUID
    stimulus_type: str
    description: str | None
    configuration: dict | None
    created_at: datetime

    class Config:
        from_attributes = True


class StimulusEventCreate(BaseModel):
    stimulus_id: uuid.UUID
    experiment_phase_id: uuid.UUID | None = None
    start_time: datetime
    end_time: datetime | None = None
    position_x: float | None = None
    position_y: float | None = None
    trajectory_dataset_version_id: uuid.UUID | None = None
    speed: float | None = None
    direction: float | None = None
    intensity: float | None = None


class StimulusEventUpdate(BaseModel):
    end_time: datetime | None = None
    position_x: float | None = None
    position_y: float | None = None
    speed: float | None = None
    direction: float | None = None
    intensity: float | None = None


class StimulusEventOut(BaseModel):
    id: uuid.UUID
    stimulus_id: uuid.UUID
    experiment_phase_id: uuid.UUID | None
    start_time: datetime
    end_time: datetime | None
    position_x: float | None
    position_y: float | None
    trajectory_dataset_version_id: uuid.UUID | None
    speed: float | None
    direction: float | None
    intensity: float | None

    class Config:
        from_attributes = True
