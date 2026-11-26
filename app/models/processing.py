"""Tools, processing runs and machine-learning models.

See [Data model](../data-model.md).
"""

import uuid
from datetime import datetime
from sqlalchemy import Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models._enums import run_status


class Tool(Base):
    """A processing step, such as "Positional Tracker". Registered the first time it runs."""

    __tablename__ = "tools"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ToolVersion(Base):
    """A version of a tool. Every run records the tool version that produced it.

    Imported data uses a `csv-import-…` label to set it apart from real runs.
    `commit_hash` and `container_image` are never filled in.
    """

    __tablename__ = "tool_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tool_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tools.id"), nullable=False)
    version_label: Mapped[str] = mapped_column(Text, nullable=False)
    commit_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    container_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MLModel(Base):
    """A machine-learning model owned by a laboratory.

    Maps to the `models` table. It is named MLModel in Python to avoid
    clashing with the `app.models` package name. No part of the pipeline
    creates or uses models yet.
    """

    __tablename__ = "models"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    laboratory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("laboratories.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    model_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcessingRun(Base):
    """One execution of a tool, the core of the system's provenance.

    `parameters` holds the settings it ran with, `runtime_info` the
    summary values it produced, and `error_message` the reason if it failed.
    `status` moves from `queued` to `running` to `succeeded` or `failed`.
    Inputs and outputs are linked through `ProcessingRunInput` and
    `ProcessingRunOutput`.
    """

    __tablename__ = "processing_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experiment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("experiments.id"), nullable=False)
    tool_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tool_versions.id"), nullable=False)
    # FK added in schema.sql via ALTER TABLE after model_versions exists (circular dependency).
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_versions.id", use_alter=True, name="fk_processing_runs_model_version"),
        nullable=True,
    )
    initiated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(run_status, nullable=False, default="queued")
    parameters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    runtime_info: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelVersion(Base):
    """A trained version of a machine-learning model. Not yet used by the pipeline."""

    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("models.id"), nullable=False)
    version_label: Mapped[str] = mapped_column(Text, nullable=False)
    hyperparameters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    artifact_file_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file_versions.id"), nullable=True
    )
    training_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_runs.id"), nullable=True
    )
    is_deprecated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
