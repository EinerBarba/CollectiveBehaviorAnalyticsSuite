import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.crud.base import get_or_404, list_all, create_obj, update_obj, soft_delete, hard_delete
from app.models import Experiment, Subject, ExperimentSubject, SubjectGroup, SubjectGroupMember, ExperimentPhase, User
from app.schemas.experiments import (
    ExperimentCreate, ExperimentUpdate, ExperimentOut,
    SubjectCreate, SubjectUpdate, SubjectOut,
    ExperimentSubjectCreate, ExperimentSubjectOut,
    SubjectGroupCreate, SubjectGroupUpdate, SubjectGroupOut,
    SubjectGroupMemberCreate, SubjectGroupMemberOut,
    ExperimentPhaseCreate, ExperimentPhaseUpdate, ExperimentPhaseOut,
)

router = APIRouter(tags=["experiments"])

@router.post("/experiments", response_model=ExperimentOut, status_code=status.HTTP_201_CREATED)
async def create_experiment(body: ExperimentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, Experiment, {**body.model_dump(), "created_by": user.id})


@router.get("/experiments", response_model=list[ExperimentOut])
async def list_experiments(
    laboratory_id: uuid.UUID | None = None, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    filters = [Experiment.laboratory_id == laboratory_id] if laboratory_id else None
    return await list_all(db, Experiment, skip=skip, limit=limit, filters=filters)


@router.get("/experiments/{experiment_id}", response_model=ExperimentOut)
async def get_experiment(experiment_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, Experiment, experiment_id)


@router.patch("/experiments/{experiment_id}", response_model=ExperimentOut)
async def update_experiment(
    experiment_id: uuid.UUID, body: ExperimentUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    exp = await get_or_404(db, Experiment, experiment_id)
    return await update_obj(db, exp, body.model_dump(exclude_unset=True))


@router.delete("/experiments/{experiment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_experiment(experiment_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    exp = await get_or_404(db, Experiment, experiment_id)
    await soft_delete(db, exp)


@router.post("/subjects", response_model=SubjectOut, status_code=status.HTTP_201_CREATED)
async def create_subject(body: SubjectCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, Subject, {**body.model_dump(), "created_by": user.id})


@router.get("/subjects", response_model=list[SubjectOut])
async def list_subjects(
    laboratory_id: uuid.UUID | None = None, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    filters = [Subject.laboratory_id == laboratory_id] if laboratory_id else None
    return await list_all(db, Subject, skip=skip, limit=limit, filters=filters)


@router.get("/subjects/{subject_id}", response_model=SubjectOut)
async def get_subject(subject_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, Subject, subject_id)


@router.patch("/subjects/{subject_id}", response_model=SubjectOut)
async def update_subject(
    subject_id: uuid.UUID, body: SubjectUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    subj = await get_or_404(db, Subject, subject_id)
    return await update_obj(db, subj, body.model_dump(exclude_unset=True))


@router.delete("/subjects/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subject(subject_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    subj = await get_or_404(db, Subject, subject_id)
    await soft_delete(db, subj)



@router.post("/experiment-subjects", response_model=ExperimentSubjectOut, status_code=status.HTTP_201_CREATED)
async def add_experiment_subject(
    body: ExperimentSubjectCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await create_obj(db, ExperimentSubject, {**body.model_dump(), "added_by": user.id})


@router.get("/experiment-subjects", response_model=list[ExperimentSubjectOut])
async def list_experiment_subjects(
    experiment_id: uuid.UUID | None = None, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    filters = [ExperimentSubject.experiment_id == experiment_id] if experiment_id else None
    return await list_all(db, ExperimentSubject, skip=skip, limit=limit, filters=filters)


@router.delete("/experiment-subjects/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_experiment_subject(link_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    link = await get_or_404(db, ExperimentSubject, link_id)
    await hard_delete(db, link)



@router.post("/subject-groups", response_model=SubjectGroupOut, status_code=status.HTTP_201_CREATED)
async def create_subject_group(body: SubjectGroupCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, SubjectGroup, body.model_dump())


@router.get("/subject-groups", response_model=list[SubjectGroupOut])
async def list_subject_groups(
    experiment_id: uuid.UUID | None = None, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    filters = [SubjectGroup.experiment_id == experiment_id] if experiment_id else None
    return await list_all(db, SubjectGroup, skip=skip, limit=limit, filters=filters)


@router.patch("/subject-groups/{group_id}", response_model=SubjectGroupOut)
async def update_subject_group(
    group_id: uuid.UUID, body: SubjectGroupUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    group = await get_or_404(db, SubjectGroup, group_id)
    return await update_obj(db, group, body.model_dump(exclude_unset=True))


@router.delete("/subject-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subject_group(group_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    group = await get_or_404(db, SubjectGroup, group_id)
    await hard_delete(db, group)



@router.post("/subject-group-members", response_model=SubjectGroupMemberOut, status_code=status.HTTP_201_CREATED)
async def add_subject_group_member(
    body: SubjectGroupMemberCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await create_obj(db, SubjectGroupMember, body.model_dump())


@router.get("/subject-group-members", response_model=list[SubjectGroupMemberOut])
async def list_subject_group_members(
    subject_group_id: uuid.UUID | None = None, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    filters = [SubjectGroupMember.subject_group_id == subject_group_id] if subject_group_id else None
    return await list_all(db, SubjectGroupMember, skip=skip, limit=limit, filters=filters)


@router.delete("/subject-group-members", status_code=status.HTTP_204_NO_CONTENT)
async def remove_subject_group_member(
    subject_group_id: uuid.UUID, experiment_subject_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    member = await db.get(SubjectGroupMember, (subject_group_id, experiment_subject_id))
    if member:
        await hard_delete(db, member)



@router.post("/experiment-phases", response_model=ExperimentPhaseOut, status_code=status.HTTP_201_CREATED)
async def create_experiment_phase(
    body: ExperimentPhaseCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await create_obj(db, ExperimentPhase, body.model_dump())


@router.get("/experiment-phases", response_model=list[ExperimentPhaseOut])
async def list_experiment_phases(
    experiment_id: uuid.UUID | None = None, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    filters = [ExperimentPhase.experiment_id == experiment_id] if experiment_id else None
    return await list_all(db, ExperimentPhase, skip=skip, limit=limit, filters=filters)


@router.patch("/experiment-phases/{phase_id}", response_model=ExperimentPhaseOut)
async def update_experiment_phase(
    phase_id: uuid.UUID, body: ExperimentPhaseUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    phase = await get_or_404(db, ExperimentPhase, phase_id)
    return await update_obj(db, phase, body.model_dump(exclude_unset=True))


@router.delete("/experiment-phases/{phase_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_experiment_phase(phase_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    phase = await get_or_404(db, ExperimentPhase, phase_id)
    await hard_delete(db, phase)
