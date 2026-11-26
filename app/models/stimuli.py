"""Stimuli and stimulus events.

These tables are available through the API but the pipeline does not use
them: the light stimulus is described by the light-tracking run instead.
"""

import uuid
from datetime import datetime
from sqlalchemy import Text, Float, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class StimulusType(Base):
    """A kind of stimulus."""

    __tablename__ = "stimulus_types"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)


class Stimulus(Base):
    """A stimulus used in an experiment, with free-form configuration."""

    __tablename__ = "stimuli"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experiment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("experiments.id"), nullable=False)
    stimulus_type: Mapped[str] = mapped_column(Text, ForeignKey("stimulus_types.key"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    configuration: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StimulusEvent(Base):
    """One occurrence of a stimulus, with its timing and optional position and motion."""

    __tablename__ = "stimulus_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stimulus_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stimuli.id"), nullable=False)
    experiment_phase_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiment_phases.id"), nullable=True
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    position_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    trajectory_dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_versions.id"), nullable=True
    )
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    direction: Mapped[float | None] = mapped_column(Float, nullable=True)
    intensity: Mapped[float | None] = mapped_column(Float, nullable=True)
