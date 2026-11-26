import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.crud.base import get_or_404, list_all, create_obj, update_obj, hard_delete
from app.models import ManualAnnotationSession, AnnotationPoint, User
from app.schemas.annotations import (
    ManualAnnotationSessionCreate, ManualAnnotationSessionUpdate, ManualAnnotationSessionOut,
    AnnotationPointCreate, AnnotationPointUpdate, AnnotationPointOut,
)

router = APIRouter(tags=["annotations"])


@router.post("/annotation-sessions", response_model=ManualAnnotationSessionOut, status_code=status.HTTP_201_CREATED)
async def create_annotation_session(
    body: ManualAnnotationSessionCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await create_obj(db, ManualAnnotationSession, {**body.model_dump(), "created_by": user.id})


@router.get("/annotation-sessions", response_model=list[ManualAnnotationSessionOut])
async def list_annotation_sessions(
    experiment_id: uuid.UUID | None = None, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    filters = [ManualAnnotationSession.experiment_id == experiment_id] if experiment_id else None
    return await list_all(db, ManualAnnotationSession, skip=skip, limit=limit, filters=filters)


@router.get("/annotation-sessions/{session_id}", response_model=ManualAnnotationSessionOut)
async def get_annotation_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, ManualAnnotationSession, session_id)


@router.patch("/annotation-sessions/{session_id}", response_model=ManualAnnotationSessionOut)
async def update_annotation_session(
    session_id: uuid.UUID,
    body: ManualAnnotationSessionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await get_or_404(db, ManualAnnotationSession, session_id)
    return await update_obj(db, session, body.model_dump(exclude_unset=True))

@router.post("/annotation-points", response_model=AnnotationPointOut, status_code=status.HTTP_201_CREATED)
async def create_annotation_point(
    body: AnnotationPointCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await create_obj(db, AnnotationPoint, {**body.model_dump(), "created_by": user.id})


@router.get("/annotation-points", response_model=list[AnnotationPointOut])
async def list_annotation_points(session_id: uuid.UUID, skip: int = 0, limit: int = 1000, db: AsyncSession = Depends(get_db)):
    return await list_all(db, AnnotationPoint, skip=skip, limit=limit, filters=[AnnotationPoint.session_id == session_id])


@router.patch("/annotation-points/{point_id}", response_model=AnnotationPointOut)
async def update_annotation_point(
    point_id: uuid.UUID, body: AnnotationPointUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    point = await get_or_404(db, AnnotationPoint, point_id)
    return await update_obj(db, point, body.model_dump(exclude_unset=True))


@router.delete("/annotation-points/{point_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_annotation_point(point_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    point = await get_or_404(db, AnnotationPoint, point_id)
    await hard_delete(db, point)
