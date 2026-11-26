from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import get_or_404, get_or_create
from app.database import get_db
from app.deps import get_current_user
from app.jobs.subject_kinematics_job import TOOL_NAME, TOOL_VERSION_LABEL, run_subject_kinematics_job
from app.models import Experiment, File, FileVersion, ProcessingRun, Tool, ToolVersion, User
from app.schemas.processing import ProcessingRunOut

router = APIRouter(tags=["subject-kinematics"])


class SubjectKinematicsRunCreate(BaseModel):
    experiment_id: uuid.UUID
    trajectory_file_version_id: uuid.UUID  # positional-tracking output CSV
    fps: float | None = Field(default=None, gt=0)  # omit to get px/frame units
    video_file_version_id: uuid.UUID | None = None  # source video, for run scoping


@router.post("/processing-runs/subject-kinematics", response_model=ProcessingRunOut, status_code=status.HTTP_201_CREATED)
async def start_subject_kinematics_run(
    body: SubjectKinematicsRunCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_or_404(db, Experiment, body.experiment_id)
    version = await get_or_404(db, FileVersion, body.trajectory_file_version_id)
    source_file = await get_or_404(db, File, version.file_id)
    if source_file.experiment_id != body.experiment_id or source_file.file_type != "csv":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trajectory CSV file version not found")

    tool = await get_or_create(
        db,
        Tool,
        name=TOOL_NAME,
        defaults={"category": "tracking", "description": "Per-subject displacement, speed, acceleration and heading"},
    )
    tool_version = await get_or_create(db, ToolVersion, tool_id=tool.id, version_label=TOOL_VERSION_LABEL)

    run = ProcessingRun(
        experiment_id=body.experiment_id,
        tool_version_id=tool_version.id,
        initiated_by=user.id,
        status="queued",
        parameters={
            "fps": body.fps,
            "trajectory_file_version_id": str(body.trajectory_file_version_id),
            **({"video_file_version_id": str(body.video_file_version_id)} if body.video_file_version_id else {}),
        },
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    background_tasks.add_task(
        run_subject_kinematics_job, run.id, body.trajectory_file_version_id, body.experiment_id, user.id, body.fps
    )
    return run
