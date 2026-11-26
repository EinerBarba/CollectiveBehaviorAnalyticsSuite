from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import get_or_404, get_or_create
from app.database import get_db
from app.deps import get_current_user
from app.jobs.manual_tracking_job import TOOL_NAME, TOOL_VERSION_LABEL, run_manual_tracking_job
from app.models import Experiment, File, FileVersion, ProcessingRun, Tool, ToolVersion, User
from app.schemas.processing import ProcessingRunOut

router = APIRouter(tags=["manual-tracking"])


class ManualTrackingRunCreate(BaseModel):
    experiment_id: uuid.UUID
    file_version_id: uuid.UUID
    center_x: float
    center_y: float
    radius_px: float = Field(gt=0)
    # All four light fields must be present together or all absent (no-stimulus video).
    first_frame: int | None = Field(default=None, ge=0)
    first_x: float | None = None
    first_y: float | None = None
    frames_per_rotation: float | None = Field(default=None, gt=0)
    direction: Literal[-1, 1] = 1

    @model_validator(mode="after")
    def _check_light_fields_consistency(self) -> "ManualTrackingRunCreate":
        light_fields = [self.first_frame, self.first_x, self.first_y, self.frames_per_rotation]
        provided = [f is not None for f in light_fields]
        if any(provided) and not all(provided):
            raise ValueError(
                "Provide all light fields (first_frame, first_x, first_y, frames_per_rotation) "
                "together, or omit all of them for a no-stimulus video."
            )
        return self


@router.post("/processing-runs/manual-tracking", response_model=ProcessingRunOut, status_code=status.HTTP_201_CREATED)
async def start_manual_tracking_run(
    body: ManualTrackingRunCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_or_404(db, Experiment, body.experiment_id)
    file_version = await get_or_404(db, FileVersion, body.file_version_id)
    source_file = await get_or_404(db, File, file_version.file_id)
    if source_file.experiment_id != body.experiment_id or source_file.file_type != "video":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video file version not found")

    tool = await get_or_create(
        db,
        Tool,
        name=TOOL_NAME,
        defaults={"category": "video-processing", "description": "Manual circular trajectory generation"},
    )
    tool_version = await get_or_create(db, ToolVersion, tool_id=tool.id, version_label=TOOL_VERSION_LABEL)
    config = body.model_dump(exclude={"experiment_id", "file_version_id"}, exclude_none=True)
    run = ProcessingRun(
        experiment_id=body.experiment_id,
        tool_version_id=tool_version.id,
        initiated_by=user.id,
        status="queued",
        parameters={**config, "source_file_version_id": str(body.file_version_id)},
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    background_tasks.add_task(
        run_manual_tracking_job,
        run.id,
        body.file_version_id,
        body.experiment_id,
        user.id,
        config,
    )
    return run