import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.crud.base import get_or_404, list_all, create_obj, update_obj, hard_delete
from app.models import (
    ProcessingRunInput,
    ProcessingRunOutput,
    ModelEvaluation,
    ModelPrediction,
    Track,
    IdentityAssignment,
    User,
)
from app.schemas.results import (
    ProcessingRunInputCreate, ProcessingRunInputOut,
    ProcessingRunOutputCreate, ProcessingRunOutputOut,
    ModelEvaluationCreate, ModelEvaluationOut,
    ModelPredictionCreate, ModelPredictionOut,
    TrackCreate, TrackUpdate, TrackOut,
    IdentityAssignmentCreate, IdentityAssignmentOut,
)

router = APIRouter(tags=["results"])



@router.post("/processing-run-inputs", response_model=ProcessingRunInputOut, status_code=status.HTTP_201_CREATED)
async def create_run_input(body: ProcessingRunInputCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, ProcessingRunInput, body.model_dump())


@router.get("/processing-run-inputs", response_model=list[ProcessingRunInputOut])
async def list_run_inputs(processing_run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await list_all(db, ProcessingRunInput, limit=500, filters=[ProcessingRunInput.processing_run_id == processing_run_id])


@router.post("/processing-run-outputs", response_model=ProcessingRunOutputOut, status_code=status.HTTP_201_CREATED)
async def create_run_output(body: ProcessingRunOutputCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, ProcessingRunOutput, body.model_dump())


@router.get("/processing-run-outputs", response_model=list[ProcessingRunOutputOut])
async def list_run_outputs(processing_run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await list_all(db, ProcessingRunOutput, limit=500, filters=[ProcessingRunOutput.processing_run_id == processing_run_id])



@router.post("/model-evaluations", response_model=ModelEvaluationOut, status_code=status.HTTP_201_CREATED)
async def create_model_evaluation(body: ModelEvaluationCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, ModelEvaluation, body.model_dump())


@router.get("/model-evaluations", response_model=list[ModelEvaluationOut])
async def list_model_evaluations(
    model_version_id: uuid.UUID | None = None, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    filters = [ModelEvaluation.model_version_id == model_version_id] if model_version_id else None
    return await list_all(db, ModelEvaluation, skip=skip, limit=limit, filters=filters)



@router.post("/model-predictions", response_model=ModelPredictionOut, status_code=status.HTTP_201_CREATED)
async def create_model_prediction(body: ModelPredictionCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, ModelPrediction, body.model_dump())


@router.post("/model-predictions/bulk", response_model=list[ModelPredictionOut], status_code=status.HTTP_201_CREATED)
async def create_model_predictions_bulk(
    bodies: list[ModelPredictionCreate], user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    objs = [ModelPrediction(**b.model_dump()) for b in bodies]
    db.add_all(objs)
    await db.commit()
    for obj in objs:
        await db.refresh(obj)
    return objs


@router.get("/model-predictions", response_model=list[ModelPredictionOut])
async def list_model_predictions(
    processing_run_id: uuid.UUID | None = None,
    dataset_version_id: uuid.UUID | None = None,
    experiment_subject_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if processing_run_id:
        filters.append(ModelPrediction.processing_run_id == processing_run_id)
    if dataset_version_id:
        filters.append(ModelPrediction.dataset_version_id == dataset_version_id)
    if experiment_subject_id:
        filters.append(ModelPrediction.experiment_subject_id == experiment_subject_id)
    return await list_all(db, ModelPrediction, skip=skip, limit=limit, filters=filters or None)


@router.delete("/model-predictions", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model_predictions_for_run(
    processing_run_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Bulk delete: clears predictions from a run before it's rerun."""
    from sqlalchemy import delete as sa_delete

    await db.execute(sa_delete(ModelPrediction).where(ModelPrediction.processing_run_id == processing_run_id))
    await db.commit()



@router.post("/tracks", response_model=TrackOut, status_code=status.HTTP_201_CREATED)
async def create_track(body: TrackCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, Track, body.model_dump())


@router.get("/tracks", response_model=list[TrackOut])
async def list_tracks(
    dataset_version_id: uuid.UUID | None = None, skip: int = 0, limit: int = 200, db: AsyncSession = Depends(get_db)
):
    filters = [Track.dataset_version_id == dataset_version_id] if dataset_version_id else None
    return await list_all(db, Track, skip=skip, limit=limit, filters=filters)


@router.get("/tracks/{track_id}", response_model=TrackOut)
async def get_track(track_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, Track, track_id)


@router.patch("/tracks/{track_id}", response_model=TrackOut)
async def update_track(track_id: uuid.UUID, body: TrackUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    track = await get_or_404(db, Track, track_id)
    return await update_obj(db, track, body.model_dump(exclude_unset=True))


@router.delete("/tracks/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_track(track_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    track = await get_or_404(db, Track, track_id)
    await hard_delete(db, track)



@router.post("/identity-assignments", response_model=IdentityAssignmentOut, status_code=status.HTTP_201_CREATED)
async def create_identity_assignment(
    body: IdentityAssignmentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await create_obj(db, IdentityAssignment, {**body.model_dump(), "assigned_by_user": user.id})


@router.get("/identity-assignments", response_model=list[IdentityAssignmentOut])
async def list_identity_assignments(
    track_id: uuid.UUID | None = None,
    experiment_subject_id: uuid.UUID | None = None,
    current_only: bool = True,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if track_id:
        filters.append(IdentityAssignment.track_id == track_id)
    if experiment_subject_id:
        filters.append(IdentityAssignment.experiment_subject_id == experiment_subject_id)
    if current_only:
        filters.append(IdentityAssignment.is_current.is_(True))
    return await list_all(db, IdentityAssignment, skip=skip, limit=limit, filters=filters or None)


@router.post("/identity-assignments/{assignment_id}/supersede", response_model=IdentityAssignmentOut)
async def supersede_identity_assignment(
    assignment_id: uuid.UUID,
    body: IdentityAssignmentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Corrects an identity assignment: creates a new row and marks the old one superseded."""
    old = await get_or_404(db, IdentityAssignment, assignment_id)
    new = await create_obj(db, IdentityAssignment, {**body.model_dump(), "assigned_by_user": user.id})
    old.is_current = False
    old.superseded_by = new.id
    await db.commit()
    return new
