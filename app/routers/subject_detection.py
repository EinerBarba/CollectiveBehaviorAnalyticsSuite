from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import get_or_404, get_or_create
from app.database import get_db
from app.deps import get_current_user
from app.jobs.subject_detection_job import TOOL_NAME, TOOL_VERSION_LABEL, run_subject_detection_job
from app.models import Experiment, File, FileVersion, ProcessingRun, Tool, ToolVersion, User
from app.schemas.processing import ProcessingRunOut

router = APIRouter(tags=["subject-detection"])


class SubjectDetectionRunCreate(BaseModel):
    experiment_id: uuid.UUID
    file_version_id: uuid.UUID  # source video
    start_frame: int = Field(default=0, ge=0)
    number_of_frames: int | None = Field(default=None, gt=0)
    frame_step: int = Field(default=1, ge=1)
    min_area: float = Field(default=50.0, gt=0)
    max_area: float = Field(default=250.0, gt=0)
    brightness_ratio: float = Field(default=0.85, gt=0, le=1)
    min_solidity: float = Field(default=0.80, gt=0, le=1)
    min_aspect_ratio: float = Field(default=0.5, gt=0)
    max_aspect_ratio: float = Field(default=2.0, gt=0)
    min_circularity: float = Field(default=0.50, gt=0, le=1)
    plate_cx: int | None = Field(default=None, gt=0)
    plate_cy: int | None = Field(default=None, gt=0)
    plate_r: int | None = Field(default=None, gt=0)


@router.post("/processing-runs/subject-detection", response_model=ProcessingRunOut, status_code=status.HTTP_201_CREATED)
async def start_subject_detection_run(
    body: SubjectDetectionRunCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_or_404(db, Experiment, body.experiment_id)
    version = await get_or_404(db, FileVersion, body.file_version_id)
    source_file = await get_or_404(db, File, version.file_id)
    if source_file.experiment_id != body.experiment_id or source_file.file_type != "video":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video file version not found")
    if body.min_area >= body.max_area:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "min_area must be less than max_area")

    tool = await get_or_create(
        db,
        Tool,
        name=TOOL_NAME,
        defaults={"category": "video-processing", "description": "Bright-spot subject detection inside the arena"},
    )
    tool_version = await get_or_create(db, ToolVersion, tool_id=tool.id, version_label=TOOL_VERSION_LABEL)

    params = body.model_dump(exclude={"experiment_id", "file_version_id"})
    run = ProcessingRun(
        experiment_id=body.experiment_id,
        tool_version_id=tool_version.id,
        initiated_by=user.id,
        status="queued",
        parameters={**params, "source_file_version_id": str(body.file_version_id)},
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    background_tasks.add_task(
        run_subject_detection_job, run.id, body.file_version_id, body.experiment_id, user.id, params
    )
    return run
