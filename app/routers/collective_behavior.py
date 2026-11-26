from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import get_or_404, get_or_create
from app.database import get_db
from app.deps import get_current_user
from app.jobs.collective_behavior_job import (
    TOOL_NAME,
    TOOL_VERSION_LABEL,
    TOOL_VERSION_LABEL_EXPERIMENT,
    run_collective_behavior_job,
    run_collective_behavior_experiment_job,
)
from app.models import Experiment, FileVersion, File, ProcessingRun, Tool, ToolVersion, User
from app.schemas.processing import ProcessingRunOut

router = APIRouter(tags=["collective-behavior"])


class CollectiveBehaviourExperimentRunCreate(BaseModel):
    experiment_id: uuid.UUID
    fps: float | None = Field(default=None, gt=0, description="Global FPS override for all videos")
    frame_step: int | None = Field(default=None, ge=1, description="Keep every Nth trajectory frame to simulate lower FPS (1=all frames)")
    window_size: int | None = Field(default=None, gt=0, description="Sliding window size in frames")
    window_step: int | None = Field(default=None, gt=0, description="Sliding window step in frames")


class StimulusConfig(BaseModel):
    omega: float = Field(description="LED angular velocity in degrees/frame (positive = clockwise)")
    theta_light_0: float = Field(default=0.0, description="Initial LED phase in degrees")


class CollectiveBehaviourRunCreate(BaseModel):
    experiment_id: uuid.UUID
    trajectory_file_version_id: uuid.UUID  # positional_tracks.csv file version
    arena_center_x: float = Field(description="Arena center x-coordinate (pixels)")
    arena_center_y: float = Field(description="Arena center y-coordinate (pixels)")
    arena_radius: float = Field(gt=0, description="Arena radius (pixels), used to normalize M")
    stimulus: StimulusConfig | None = Field(
        default=None,
        description="LED stimulus parameters; omit or pass null when there is no stimulus",
    )
    fps: float | None = Field(
        default=None, gt=0,
        description="Frame rate override; falls back to DatasetSpatialMetadata.sampling_rate_hz",
    )
    frame_step: int | None = Field(default=None, ge=1, description="Keep every Nth trajectory frame to simulate lower FPS")
    window_size: int | None = Field(default=None, gt=0, description="Sliding window size in frames")
    window_step: int | None = Field(default=None, gt=0, description="Sliding window step in frames")
    video_file_version_id: uuid.UUID | None = None  # source video, for run scoping


@router.post(
    "/processing-runs/collective-behavior",
    response_model=ProcessingRunOut,
    status_code=status.HTTP_201_CREATED,
)
async def start_collective_behavior_run(
    body: CollectiveBehaviourRunCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_or_404(db, Experiment, body.experiment_id)

    # Verify the trajectory file belongs to this experiment
    traj_version = await get_or_404(db, FileVersion, body.trajectory_file_version_id)
    traj_file = await get_or_404(db, File, traj_version.file_id)
    if traj_file.experiment_id != body.experiment_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trajectory file version not found")

    tool = await get_or_create(
        db,
        Tool,
        name=TOOL_NAME,
        defaults={
            "category": "analysis",
            "description": "Sliding-window order parameters, GMM clustering, and Markov chain analysis of collective behavior",
        },
    )
    tool_version = await get_or_create(
        db, ToolVersion, tool_id=tool.id, version_label=TOOL_VERSION_LABEL
    )

    params = {
        "arena_center_x": body.arena_center_x,
        "arena_center_y": body.arena_center_y,
        "arena_radius": body.arena_radius,
        "stimulus": body.stimulus.model_dump() if body.stimulus else None,
        "fps": body.fps,
        "trajectory_file_version_id": str(body.trajectory_file_version_id),
        **({"video_file_version_id": str(body.video_file_version_id)} if body.video_file_version_id else {}),
        **({"frame_step": body.frame_step} if body.frame_step and body.frame_step > 1 else {}),
        **({"window_size": body.window_size} if body.window_size else {}),
        **({"window_step": body.window_step} if body.window_step else {}),
    }

    run = ProcessingRun(
        experiment_id=body.experiment_id,
        tool_version_id=tool_version.id,
        initiated_by=user.id,
        status="queued",
        parameters=params,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    background_tasks.add_task(
        run_collective_behavior_job,
        run.id,
        body.trajectory_file_version_id,
        body.experiment_id,
        user.id,
        params,
    )
    return run


@router.post(
    "/processing-runs/collective-behavior-experiment",
    response_model=ProcessingRunOut,
    status_code=status.HTTP_201_CREATED,
)
async def start_collective_behavior_experiment_run(
    body: CollectiveBehaviourExperimentRunCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_or_404(db, Experiment, body.experiment_id)

    tool = await get_or_create(
        db,
        Tool,
        name=TOOL_NAME,
        defaults={
            "category": "analysis",
            "description": "Condition-split GMM + Markov collective behavior analysis",
        },
    )
    tool_version = await get_or_create(
        db, ToolVersion, tool_id=tool.id, version_label=TOOL_VERSION_LABEL_EXPERIMENT
    )

    params = {
        "fps": body.fps,
        **({"frame_step": body.frame_step} if body.frame_step and body.frame_step > 1 else {}),
        **({"window_size": body.window_size} if body.window_size else {}),
        **({"window_step": body.window_step} if body.window_step else {}),
    }
    run = ProcessingRun(
        experiment_id=body.experiment_id,
        tool_version_id=tool_version.id,
        initiated_by=user.id,
        status="queued",
        parameters=params,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    background_tasks.add_task(
        run_collective_behavior_experiment_job,
        run.id,
        body.experiment_id,
        user.id,
        params,
    )
    return run
