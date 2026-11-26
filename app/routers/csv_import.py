from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import get_or_404, get_or_create
from app.database import get_db
from app.deps import get_current_user
from app.jobs.csv_import_job import TOOL_NAME, TOOL_VERSION_LABEL, run_csv_import_job
from app.models import Experiment, ProcessingRun, Tool, ToolVersion, User
from app.schemas.processing import ProcessingRunOut

router = APIRouter(tags=["csv-import"])


@router.post("/processing-runs/csv-import", response_model=ProcessingRunOut, status_code=status.HTTP_201_CREATED)
async def import_position_csv(
    background_tasks: BackgroundTasks,
    experiment_id: uuid.UUID = Form(...),
    fps: float | None = Form(default=None),
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_or_404(db, Experiment, experiment_id)

    file_data: dict[str, bytes] = {}
    for f in files:
        file_data[f.filename or "unknown.csv"] = await f.read()

    tool = await get_or_create(
        db,
        Tool,
        name=TOOL_NAME,
        defaults={"category": "import", "description": "Import subject positions from external CSV files"},
    )
    tv = await get_or_create(db, ToolVersion, tool_id=tool.id, version_label=TOOL_VERSION_LABEL)

    run = ProcessingRun(
        experiment_id=experiment_id,
        tool_version_id=tv.id,
        initiated_by=user.id,
        status="queued",
        parameters={"fps": fps, "file_count": len(file_data)},
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    background_tasks.add_task(run_csv_import_job, run.id, experiment_id, user.id, fps, file_data)
    return run
