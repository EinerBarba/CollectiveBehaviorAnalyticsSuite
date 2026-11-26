"""Named metrics and their computed values."""

import uuid
from datetime import datetime
from sqlalchemy import Text, Integer, Float, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models._enums import metric_value_type, metric_scope


class MetricDefinition(Base):
    """A metric's key, display name, unit and scope (`individual` or `group`).

    Registered the first time a job records the metric, and not updated after.
    """

    __tablename__ = "metric_definitions"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_type: Mapped[str] = mapped_column(metric_value_type, nullable=False)
    scope: Mapped[str] = mapped_column(metric_scope, nullable=False)


class MetricResult(Base):
    """One computed metric value, tied to the run and dataset version it came from.

    Per-track kinematics summaries name their track in
    `value_json["track_label"]` rather than in `experiment_subject_id`.
    """

    __tablename__ = "metric_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dataset_versions.id"), nullable=False)
    processing_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("processing_runs.id"), nullable=False)
    metric_key: Mapped[str] = mapped_column(Text, ForeignKey("metric_definitions.key"), nullable=False)
    experiment_subject_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiment_subjects.id"), nullable=True
    )
    subject_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("subject_groups.id"), nullable=True)
    experiment_phase_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiment_phases.id"), nullable=True
    )
    value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ComparisonRun(Base):
    """A comparison of a candidate dataset version against a reference. Not yet used by the pipeline."""

    __tablename__ = "comparison_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experiment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("experiments.id"), nullable=False)
    reference_dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_versions.id"), nullable=False
    )
    candidate_dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_versions.id"), nullable=False
    )
    processing_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("processing_runs.id"), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ComparisonResult(Base):
    """One measured difference from a comparison run. Not yet used by the pipeline."""

    __tablename__ = "comparison_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comparison_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("comparison_runs.id"), nullable=False)
    experiment_subject_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiment_subjects.id"), nullable=True
    )
    metric_name: Mapped[str] = mapped_column(Text, nullable=False)
    value_numeric: Mapped[float] = mapped_column(Float, nullable=False)
    frame_range_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frame_range_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
