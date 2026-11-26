from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import storage
from app.crud.base import get_or_404
from app.database import get_db
from app.deps import get_current_user
from app.models import File, FileVersion, User
from app.tracking.io import parse_detections
from app.tracking.positional_tracker import track_unclaimed_detections

router = APIRouter(tags=["trajectory-edit"])

PROGRESS_MIME = "application/vnd.kani.trajectory-progress+json"


class TrajectoryEditSave(BaseModel):
    file_version_id: uuid.UUID
    csv_content: str


@router.post("/trajectories/save-edit", status_code=status.HTTP_201_CREATED)
async def save_trajectory_edit(
    body: TrajectoryEditSave,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    old_version = await get_or_404(db, FileVersion, body.file_version_id)
    file_obj = await get_or_404(db, File, old_version.file_id)

    existing_numbers = (
        await db.execute(
            select(FileVersion.version_number).where(FileVersion.file_id == file_obj.id)
        )
    ).scalars().all()
    new_number = max(existing_numbers, default=0) + 1

    csv_bytes = body.csv_content.encode("utf-8")
    key, checksum, size = storage.save_bytes(
        csv_bytes,
        f"experiments/{file_obj.experiment_id}/trajectory-edits",
        f"positional_tracks_v{new_number}.csv",
    )

    old_version.is_current = False
    new_version = FileVersion(
        file_id=file_obj.id,
        version_number=new_number,
        storage_bucket=storage.STORAGE_BUCKET,
        storage_key=key,
        mime_type="text/csv",
        size_bytes=size,
        checksum_sha256=checksum,
        uploaded_by=user.id,
        is_current=True,
    )
    db.add(new_version)
    await db.flush()
    file_obj.current_version_id = new_version.id
    await db.commit()
    await db.refresh(new_version)
    return {"file_version_id": str(new_version.id)}


class TrajectoryProgressSave(BaseModel):
    file_version_id: uuid.UUID
    progress_json: str


@router.post("/trajectories/save-progress", status_code=status.HTTP_201_CREATED)
async def save_trajectory_progress(
    body: TrajectoryProgressSave,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    old_version = await get_or_404(db, FileVersion, body.file_version_id)
    file_obj = await get_or_404(db, File, old_version.file_id)

    existing_numbers = (
        await db.execute(
            select(FileVersion.version_number).where(FileVersion.file_id == file_obj.id)
        )
    ).scalars().all()
    new_number = max(existing_numbers, default=0) + 1

    json_bytes = body.progress_json.encode("utf-8")
    key, checksum, size = storage.save_bytes(
        json_bytes,
        f"experiments/{file_obj.experiment_id}/trajectory-progress",
        f"trajectory_progress_{new_number}.json",
    )

    new_version = FileVersion(
        file_id=file_obj.id,
        version_number=new_number,
        storage_bucket=storage.STORAGE_BUCKET,
        storage_key=key,
        mime_type=PROGRESS_MIME,
        size_bytes=size,
        checksum_sha256=checksum,
        uploaded_by=user.id,
        is_current=False,
    )
    db.add(new_version)
    await db.commit()
    await db.refresh(new_version)
    return {"file_version_id": str(new_version.id)}


class GenerateNextTracks(BaseModel):
    detections_file_version_id: uuid.UUID
    num_tracks: int = Field(gt=0, le=1000)
    max_distance: float = Field(gt=0)
    max_missed_frames: int = Field(ge=0)
    claimed: list[tuple[int, float, float]]
    claim_radius: float = Field(default=6.0, gt=0)


@router.post("/trajectories/generate-next")
async def generate_next_tracks(
    body: GenerateNextTracks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    version = await get_or_404(db, FileVersion, body.detections_file_version_id)
    try:
        detections = parse_detections(storage.full_path(version.storage_key).read_bytes())
    except (OSError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Could not read detections: {exc}") from exc

    claimed: dict[int, list[tuple[float, float]]] = {}
    for frame, x, y in body.claimed:
        claimed.setdefault(frame, []).append((x, y))

    tracks = await asyncio.to_thread(
        track_unclaimed_detections,
        detections, claimed, body.num_tracks, body.max_distance, body.max_missed_frames, body.claim_radius,
    )
    return {
        "tracks": [
            [[p.frame, p.x, p.y, p.is_predicted] for p in points]
            for points in tracks.values()
        ]
    }


@router.get("/trajectories/progress-list")
async def list_trajectory_progress(
    file_version_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    version = await get_or_404(db, FileVersion, file_version_id)
    rows = (
        await db.execute(
            select(FileVersion)
            .where(FileVersion.file_id == version.file_id, FileVersion.mime_type == PROGRESS_MIME)
            .order_by(FileVersion.uploaded_at.desc())
        )
    ).scalars().all()

    # Only offer progress saves that belong to the tracking file that is loaded
    result = []
    for r in rows:
        try:
            data = json.loads(storage.full_path(r.storage_key).read_bytes())
        except (OSError, ValueError):
            continue  # Unloadable save
        source = data.get("source_file_version_id") if isinstance(data, dict) else None
        if source is not None and source != str(file_version_id):
            continue
        result.append(
            {
                "file_version_id": str(r.id),
                "version_number": r.version_number,
                "uploaded_at": r.uploaded_at.isoformat(),
            }
        )
    return result
