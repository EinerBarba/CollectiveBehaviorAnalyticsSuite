"""Datasets: named, versioned groups of files with a known meaning.

See [Data model](../data-model.md).
"""

import uuid
from datetime import datetime
from sqlalchemy import Text, Boolean, Integer, Numeric, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models._enums import dataset_origin, dataset_status


class DatasetType(Base):
    """A kind of dataset, such as `subject_detections`. Registered the first time a job uses it."""

    __tablename__ = "dataset_types"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)


class Dataset(Base):
    """A dataset of one type within an experiment.

    `origin` records how it was made (manual, automatic, derived or
    imported). `is_ground_truth` exists for marking reference data but no
    code sets it.
    """

    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experiment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("experiments.id"), nullable=False)
    dataset_type: Mapped[str] = mapped_column(Text, ForeignKey("dataset_types.key"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin: Mapped[str] = mapped_column(dataset_origin, nullable=False)
    is_ground_truth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(dataset_status, nullable=False, default="draft")
    # FK added in schema.sql via ALTER TABLE after dataset_versions exists (circular dependency).
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_versions.id", use_alter=True, name="fk_datasets_current_version"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DatasetVersion(Base):
    """One version of a dataset. Runs record their outputs as dataset versions.

    `schema_version` names the format of its files, for example
    `positional-tracks-1.0`.
    """

    __tablename__ = "dataset_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("datasets.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DatasetSpatialMetadata(Base):
    """Coordinate system, units, sampling rate and frame range of a dataset version.

    Keyed by dataset version ID.
    """

    __tablename__ = "dataset_spatial_metadata"

    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_versions.id"), primary_key=True
    )
    coordinate_system: Mapped[str | None] = mapped_column(Text, nullable=True)
    sampling_rate_hz: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    units: Mapped[str | None] = mapped_column(Text, nullable=True)
    frame_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frame_end: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DatasetFile(Base):
    """Links a dataset version to one file version, with a role such as `primary` or `windows`."""

    __tablename__ = "dataset_files"

    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_versions.id"), primary_key=True
    )
    file_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file_versions.id"), primary_key=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False, default="primary")
