from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import get_or_404, get_or_create
from app.database import get_db
from app.deps import get_current_user
from app.jobs.positional_tracking_job import TOOL_NAME, TOOL_VERSION_LABEL, run_positional_tracking_job
from app.models import Experiment, File, FileVersion, ProcessingRun, Tool, ToolVersion, User
from app.schemas.processing import ProcessingRunOut

router = APIRouter(tags=["positional-tracking"])


class PositionalTrackingRunCreate(BaseModel):
    experiment_id: uuid.UUID
    file_version_id: uuid.UUID  # source video
    detections_file_version_id: uuid.UUID  # JSON detection artifact
    max_distance: float = Field(default=50.0, gt=0)
    max_missed_frames: int = Field(default=5, ge=0)
    max_tracks: int | None = Field(default=None, gt=0)  # number of subjects: no more tracks are ever created beyond this; omit for unlimited
    fps: float | None = Field(default=None, gt=0)  # optional; falls back to video metadata


async def _experiment_file_version(db: AsyncSession, version_id: uuid.UUID, experiment_id: uuid.UUID, file_type: str):
    version = await get_or_404(db, FileVersion, version_id)
    file_ = await get_or_404(db, File, version.file_id)
    if file_.experiment_id != experiment_id or file_.file_type != file_type:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{file_type} file version not found")
    return version


@router.post("/processing-runs/positional-tracking", response_model=ProcessingRunOut, status_code=status.HTTP_201_CREATED)
async def start_positional_tracking_run(
    body: PositionalTrackingRunCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_or_404(db, Experiment, body.experiment_id)
    await _experiment_file_version(db, body.file_version_id, body.experiment_id, "video")
    await _experiment_file_version(db, body.detections_file_version_id, body.experiment_id, "json")

    tool = await get_or_create(
        db,
        Tool,
        name=TOOL_NAME,
        defaults={"category": "tracking", "description": "Positional multi-object tracking of stored detections"},
    )
    tool_version = await get_or_create(db, ToolVersion, tool_id=tool.id, version_label=TOOL_VERSION_LABEL)

    params = body.model_dump(exclude={"experiment_id", "file_version_id", "detections_file_version_id"})
    run = ProcessingRun(
        experiment_id=body.experiment_id,
        tool_version_id=tool_version.id,
        initiated_by=user.id,
        status="queued",
        parameters={
            **params,
            "source_file_version_id": str(body.file_version_id),
            "detections_file_version_id": str(body.detections_file_version_id),
        },
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    background_tasks.add_task(
        run_positional_tracking_job,
        run.id,
        body.detections_file_version_id,
        body.file_version_id,
        body.experiment_id,
        user.id,
        params,
    )
    return run
