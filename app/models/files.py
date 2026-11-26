"""Files and their versions. See [Data model](../data-model.md)."""

import uuid
from datetime import datetime
from sqlalchemy import Text, Boolean, Integer, BigInteger, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models._enums import file_type_enum


class File(Base):
    """A logical file, such as an uploaded video or a run's output.

    The contents live in its versions. `current_version_id` points at the
    version to use by default. `is_raw` marks original uploads rather than
    derived results.
    """

    __tablename__ = "files"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("experiments.id"), nullable=True)
    file_type: Mapped[str] = mapped_column(file_type_enum, nullable=False)
    logical_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_raw: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # FK added in schema.sql via ALTER TABLE after file_versions exists (circular dependency).
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file_versions.id", use_alter=True, name="fk_files_current_version"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FileVersion(Base):
    """One stored version of a file's contents.

    New versions are added, never overwritten. `storage_key` locates the
    bytes on disk, and `checksum_sha256` lets them be verified.
    `is_current` marks the version in use. Trajectory progress saves are
    stored as versions too, with `is_current` False and their own MIME type.
    """

    __tablename__ = "file_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_bucket: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
