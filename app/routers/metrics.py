import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.crud.base import get_or_404, list_all, create_obj
from app.models import MetricDefinition, MetricResult, ComparisonRun, ComparisonResult, User
from app.schemas.metrics import (
    MetricDefinitionOut,
    MetricResultCreate, MetricResultOut,
    ComparisonRunCreate, ComparisonRunOut,
    ComparisonResultCreate, ComparisonResultOut,
)

router = APIRouter(tags=["metrics"])



@router.get("/metric-definitions", response_model=list[MetricDefinitionOut])
async def list_metric_definitions(db: AsyncSession = Depends(get_db)):
    return await list_all(db, MetricDefinition, limit=500)



@router.post("/metric-results", response_model=MetricResultOut, status_code=status.HTTP_201_CREATED)
async def create_metric_result(body: MetricResultCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, MetricResult, body.model_dump())


@router.get("/metric-results", response_model=list[MetricResultOut])
async def list_metric_results(
    dataset_version_id: uuid.UUID | None = None,
    processing_run_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if dataset_version_id:
        filters.append(MetricResult.dataset_version_id == dataset_version_id)
    if processing_run_id:
        filters.append(MetricResult.processing_run_id == processing_run_id)
    return await list_all(db, MetricResult, skip=skip, limit=limit, filters=filters or None)



@router.post("/comparison-runs", response_model=ComparisonRunOut, status_code=status.HTTP_201_CREATED)
async def create_comparison_run(body: ComparisonRunCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, ComparisonRun, {**body.model_dump(), "created_by": user.id})


@router.get("/comparison-runs", response_model=list[ComparisonRunOut])
async def list_comparison_runs(
    experiment_id: uuid.UUID | None = None, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    filters = [ComparisonRun.experiment_id == experiment_id] if experiment_id else None
    return await list_all(db, ComparisonRun, skip=skip, limit=limit, filters=filters)


@router.get("/comparison-runs/{run_id}", response_model=ComparisonRunOut)
async def get_comparison_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, ComparisonRun, run_id)



@router.post("/comparison-results", response_model=ComparisonResultOut, status_code=status.HTTP_201_CREATED)
async def create_comparison_result(
    body: ComparisonResultCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await create_obj(db, ComparisonResult, body.model_dump())


@router.get("/comparison-results", response_model=list[ComparisonResultOut])
async def list_comparison_results(comparison_run_id: uuid.UUID, skip: int = 0, limit: int = 500, db: AsyncSession = Depends(get_db)):
    return await list_all(
        db, ComparisonResult, skip=skip, limit=limit, filters=[ComparisonResult.comparison_run_id == comparison_run_id]
    )
