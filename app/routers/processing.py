import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy import select, or_, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.crud.base import get_or_404, list_all, create_obj, update_obj, hard_delete
from app.models import Tool, ToolVersion, MLModel, ModelVersion, ProcessingRun, User, Experiment, RoleAssignment
from app.schemas.processing import (
    ToolCreate, ToolUpdate, ToolOut,
    ToolVersionCreate, ToolVersionUpdate, ToolVersionOut,
    MLModelCreate, MLModelUpdate, MLModelOut,
    ModelVersionCreate, ModelVersionUpdate, ModelVersionOut,
    ProcessingRunCreate, ProcessingRunUpdate, ProcessingRunOut,
    AccessibleRunOut, ExperimentRunSummary,
)

router = APIRouter(tags=["processing"])



@router.post("/tools", response_model=ToolOut, status_code=status.HTTP_201_CREATED)
async def create_tool(body: ToolCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, Tool, body.model_dump())


@router.get("/tools", response_model=list[ToolOut])
async def list_tools(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await list_all(db, Tool, skip=skip, limit=limit)


@router.get("/tools/{tool_id}", response_model=ToolOut)
async def get_tool(tool_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, Tool, tool_id)


@router.patch("/tools/{tool_id}", response_model=ToolOut)
async def update_tool(tool_id: uuid.UUID, body: ToolUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    tool = await get_or_404(db, Tool, tool_id)
    return await update_obj(db, tool, body.model_dump(exclude_unset=True))


@router.delete("/tools/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(tool_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    tool = await get_or_404(db, Tool, tool_id)
    await hard_delete(db, tool)



@router.post("/tool-versions", response_model=ToolVersionOut, status_code=status.HTTP_201_CREATED)
async def create_tool_version(body: ToolVersionCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, ToolVersion, body.model_dump())


@router.get("/tool-versions", response_model=list[ToolVersionOut])
async def list_tool_versions(tool_id: uuid.UUID, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await list_all(db, ToolVersion, skip=skip, limit=limit, filters=[ToolVersion.tool_id == tool_id])


@router.get("/tool-versions/{version_id}", response_model=ToolVersionOut)
async def get_tool_version(version_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, ToolVersion, version_id)


@router.patch("/tool-versions/{version_id}", response_model=ToolVersionOut)
async def update_tool_version(
    version_id: uuid.UUID, body: ToolVersionUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    version = await get_or_404(db, ToolVersion, version_id)
    return await update_obj(db, version, body.model_dump(exclude_unset=True))


@router.delete("/tool-versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool_version(version_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    version = await get_or_404(db, ToolVersion, version_id)
    await hard_delete(db, version)



@router.post("/models", response_model=MLModelOut, status_code=status.HTTP_201_CREATED)
async def create_model(body: MLModelCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, MLModel, {**body.model_dump(), "created_by": user.id})


@router.get("/models", response_model=list[MLModelOut])
async def list_models(
    laboratory_id: uuid.UUID | None = None, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    filters = [MLModel.laboratory_id == laboratory_id] if laboratory_id else None
    return await list_all(db, MLModel, skip=skip, limit=limit, filters=filters)


@router.get("/models/{model_id}", response_model=MLModelOut)
async def get_model(model_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, MLModel, model_id)


@router.patch("/models/{model_id}", response_model=MLModelOut)
async def update_model(
    model_id: uuid.UUID, body: MLModelUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    model = await get_or_404(db, MLModel, model_id)
    return await update_obj(db, model, body.model_dump(exclude_unset=True))


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(model_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    model = await get_or_404(db, MLModel, model_id)
    await hard_delete(db, model)



@router.post("/model-versions", response_model=ModelVersionOut, status_code=status.HTTP_201_CREATED)
async def create_model_version(body: ModelVersionCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, ModelVersion, {**body.model_dump(), "created_by": user.id})


@router.get("/model-versions", response_model=list[ModelVersionOut])
async def list_model_versions(model_id: uuid.UUID, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await list_all(db, ModelVersion, skip=skip, limit=limit, filters=[ModelVersion.model_id == model_id])


@router.get("/model-versions/{version_id}", response_model=ModelVersionOut)
async def get_model_version(version_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, ModelVersion, version_id)


@router.patch("/model-versions/{version_id}", response_model=ModelVersionOut)
async def update_model_version(
    version_id: uuid.UUID, body: ModelVersionUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    version = await get_or_404(db, ModelVersion, version_id)
    return await update_obj(db, version, body.model_dump(exclude_unset=True))



@router.post("/processing-runs", response_model=ProcessingRunOut, status_code=status.HTTP_201_CREATED)
async def create_processing_run(body: ProcessingRunCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_obj(db, ProcessingRun, {**body.model_dump(), "initiated_by": user.id})


@router.get("/processing-runs", response_model=list[ProcessingRunOut])
async def list_processing_runs(
    experiment_id: uuid.UUID | None = None, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
):
    filters = [ProcessingRun.experiment_id == experiment_id] if experiment_id else None
    return await list_all(db, ProcessingRun, skip=skip, limit=limit, filters=filters)


@router.get("/processing-runs/accessible", response_model=list[AccessibleRunOut])
async def list_accessible_runs(
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(
            ProcessingRun.id,
            ProcessingRun.experiment_id,
            Experiment.title.label("experiment_title"),
            Tool.name.label("tool_name"),
            ProcessingRun.status,
            ProcessingRun.created_at,
        )
        .join(Experiment, ProcessingRun.experiment_id == Experiment.id)
        .join(ToolVersion, ProcessingRun.tool_version_id == ToolVersion.id)
        .join(Tool, ToolVersion.tool_id == Tool.id)
        .where(
            ProcessingRun.status == "succeeded",
            Experiment.deleted_at.is_(None),
        )
        .order_by(ProcessingRun.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    if not user.is_system_admin:
        stmt = stmt.where(
            or_(
                ProcessingRun.initiated_by == user.id,
                Experiment.created_by == user.id,
                exists(
                    select(RoleAssignment.id).where(
                        RoleAssignment.user_id == user.id,
                        RoleAssignment.scope_type == "global",
                        RoleAssignment.revoked_at.is_(None),
                    )
                ),
                exists(
                    select(RoleAssignment.id).where(
                        RoleAssignment.user_id == user.id,
                        RoleAssignment.scope_type == "laboratory",
                        RoleAssignment.scope_id == Experiment.laboratory_id,
                        RoleAssignment.revoked_at.is_(None),
                    )
                ),
                exists(
                    select(RoleAssignment.id).where(
                        RoleAssignment.user_id == user.id,
                        RoleAssignment.scope_type == "experiment",
                        RoleAssignment.scope_id == Experiment.id,
                        RoleAssignment.revoked_at.is_(None),
                    )
                ),
            )
        )
    rows = (await db.execute(stmt)).all()
    return [
        AccessibleRunOut(
            id=r.id,
            experiment_id=r.experiment_id,
            experiment_title=r.experiment_title,
            tool_name=r.tool_name,
            status=r.status,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/processing-runs/by-experiment/{experiment_id}", response_model=list[ExperimentRunSummary])
async def list_runs_by_experiment(
    experiment_id: uuid.UUID,
    file_version_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    """All processing runs for one experiment, newest first, annotated with tool name.

    Pass file_version_id to restrict to runs whose parameters contain
    source_file_version_id or video_file_version_id matching that value.
    """
    stmt = (
        select(
            ProcessingRun.id,
            ProcessingRun.status,
            ProcessingRun.created_at,
            ProcessingRun.parameters,
            ProcessingRun.runtime_info,
            ProcessingRun.error_message,
            Tool.name.label("tool_name"),
        )
        .join(ToolVersion, ProcessingRun.tool_version_id == ToolVersion.id)
        .join(Tool, ToolVersion.tool_id == Tool.id)
        .where(ProcessingRun.experiment_id == experiment_id)
        .order_by(ProcessingRun.created_at.desc())
    )
    if file_version_id is not None:
        fvid = str(file_version_id)
        stmt = stmt.where(
            or_(
                ProcessingRun.parameters["source_file_version_id"].astext == fvid,
                ProcessingRun.parameters["video_file_version_id"].astext == fvid,
            )
        )
    rows = (await db.execute(stmt)).all()
    return [
        ExperimentRunSummary(
            id=r.id,
            tool_name=r.tool_name,
            status=r.status,
            created_at=r.created_at,
            parameters=r.parameters,
            runtime_info=r.runtime_info,
            error_message=r.error_message,
        )
        for r in rows
    ]


@router.get("/processing-runs/{run_id}/progress")
async def get_processing_run_progress(
    run_id: uuid.UUID,
    user: User = Depends(get_current_user),
) -> dict:
    from app.progress import get_progress
    return get_progress(str(run_id))


@router.get("/processing-runs/{run_id}", response_model=ProcessingRunOut)
async def get_processing_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_or_404(db, ProcessingRun, run_id)


@router.patch("/processing-runs/{run_id}", response_model=ProcessingRunOut)
async def update_processing_run(
    run_id: uuid.UUID, body: ProcessingRunUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    run = await get_or_404(db, ProcessingRun, run_id)
    return await update_obj(db, run, body.model_dump(exclude_unset=True))
