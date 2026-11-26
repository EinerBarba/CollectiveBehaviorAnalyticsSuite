"""Generic database helpers shared by the routers and jobs.

Models with a `deleted_at` column support soft delete: the row stays in the
database but is hidden by `get_or_404` and `list_all`.
"""

import uuid
from datetime import datetime, timezone
from typing import Type, TypeVar, Sequence

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ModelT = TypeVar("ModelT")


async def get_or_404(db: AsyncSession, model: Type[ModelT], id_: uuid.UUID) -> ModelT:
    """Load a row by primary key, treating soft-deleted rows as missing.

    Args:
        db: Database session.
        model: The model class.
        id_: The primary key.

    Returns:
        The row.

    Raises:
        HTTPException: 404 if the row does not exist or is soft-deleted.
    """
    obj = await db.get(model, id_)
    if obj is None or getattr(obj, "deleted_at", None) is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return obj


async def get_or_404_including_deleted(db: AsyncSession, model: Type[ModelT], id_: uuid.UUID) -> ModelT:
    """Load a row by primary key, including soft-deleted rows.

    Raises:
        HTTPException: 404 if the row does not exist.
    """
    obj = await db.get(model, id_)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return obj


async def list_all(
    db: AsyncSession,
    model: Type[ModelT],
    *,
    skip: int = 0,
    limit: int = 100,
    filters: Sequence | None = None,
) -> Sequence[ModelT]:
    """List rows of a model, skipping soft-deleted ones.

    Args:
        db: Database session.
        model: The model class.
        skip: Rows to skip, for paging.
        limit: Most rows to return.
        filters: Extra SQLAlchemy conditions, all of which must hold.

    Returns:
        The matching rows.
    """
    stmt = select(model)
    if filters:
        for cond in filters:
            stmt = stmt.where(cond)
    if hasattr(model, "deleted_at"):
        stmt = stmt.where(model.deleted_at.is_(None))
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


async def create_obj(db: AsyncSession, model: Type[ModelT], data: dict) -> ModelT:
    """Create a row, commit, and return it with server defaults filled in."""
    obj = model(**data)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def update_obj(db: AsyncSession, obj: ModelT, data: dict) -> ModelT:
    """Set fields on a row and commit. Updates `updated_at` if the model has one."""
    for key, value in data.items():
        setattr(obj, key, value)
    if hasattr(obj, "updated_at"):
        obj.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    return obj


async def soft_delete(db: AsyncSession, obj) -> None:
    """Mark a row as deleted by setting `deleted_at`, and commit.

    Raises:
        HTTPException: 400 if the model has no `deleted_at` column.
    """
    if not hasattr(obj, "deleted_at"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Resource does not support soft-delete")
    obj.deleted_at = datetime.now(timezone.utc)
    await db.commit()


async def hard_delete(db: AsyncSession, obj) -> None:
    """Remove a row from the database permanently, and commit."""
    await db.delete(obj)
    await db.commit()


async def get_or_create(db: AsyncSession, model: Type[ModelT], defaults: dict | None = None, **lookup) -> ModelT:
    """Find a row matching `lookup`, or create it.

    This is how tools, tool versions, dataset types and metric definitions are
    registered the first time a job uses them. A new row is flushed but not
    committed, so it becomes permanent with the caller's commit.

    Args:
        db: Database session.
        model: The model class.
        defaults: Extra fields to set only when creating.
        **lookup (Any): Field values that identify the row.

    Returns:
        The existing or new row.
    """
    stmt = select(model)
    for key, value in lookup.items():
        stmt = stmt.where(getattr(model, key) == value)
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    if obj is not None:
        return obj
    obj = model(**{**lookup, **(defaults or {})})
    db.add(obj)
    await db.flush()
    return obj
