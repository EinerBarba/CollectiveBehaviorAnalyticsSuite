import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.crud.base import get_or_404, list_all, create_obj, update_obj, soft_delete
from app.models import Laboratory, Role, RoleAssignment, User
from app.schemas.org import (
    LaboratoryCreate,
    LaboratoryUpdate,
    LaboratoryOut,
    RoleOut,
    RoleAssignmentCreate,
    RoleAssignmentOut,
)

router = APIRouter(tags=["org"])



@router.post("/laboratories", response_model=LaboratoryOut, status_code=status.HTTP_201_CREATED)
async def create_laboratory(body: LaboratoryCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, Laboratory, {**body.model_dump(), "created_by": user.id})


@router.get("/laboratories", response_model=list[LaboratoryOut])
async def list_laboratories(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await list_all(db, Laboratory, skip=skip, limit=limit)


@router.get("/laboratories/{laboratory_id}", response_model=LaboratoryOut)
async def get_laboratory(laboratory_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, Laboratory, laboratory_id)


@router.patch("/laboratories/{laboratory_id}", response_model=LaboratoryOut)
async def update_laboratory(
    laboratory_id: uuid.UUID, body: LaboratoryUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    lab = await get_or_404(db, Laboratory, laboratory_id)
    return await update_obj(db, lab, body.model_dump(exclude_unset=True))


@router.delete("/laboratories/{laboratory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_laboratory(laboratory_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    lab = await get_or_404(db, Laboratory, laboratory_id)
    await soft_delete(db, lab)



@router.get("/roles", response_model=list[RoleOut])
async def list_roles(db: AsyncSession = Depends(get_db)):
    return await list_all(db, Role, limit=500)



@router.post("/role-assignments", response_model=RoleAssignmentOut, status_code=status.HTTP_201_CREATED)
async def create_role_assignment(
    body: RoleAssignmentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await create_obj(db, RoleAssignment, {**body.model_dump(), "granted_by": user.id})


@router.get("/role-assignments", response_model=list[RoleAssignmentOut])
async def list_role_assignments(
    user_id: uuid.UUID | None = None, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    filters = [RoleAssignment.user_id == user_id] if user_id else None
    return await list_all(db, RoleAssignment, skip=skip, limit=limit, filters=filters)


@router.post("/role-assignments/{assignment_id}/revoke", response_model=RoleAssignmentOut)
async def revoke_role_assignment(assignment_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from datetime import datetime, timezone

    assignment = await get_or_404(db, RoleAssignment, assignment_id)
    return await update_obj(db, assignment, {"revoked_at": datetime.now(timezone.utc)})
