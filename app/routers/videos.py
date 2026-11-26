from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File as UploadFileParameter, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import delete as sa_delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.crud.base import get_or_404
from app.database import get_db
from app.deps import get_current_admin, get_current_user
from app.models import (
    AnnotationPoint,
    ComparisonResult,
    ComparisonRun,
    Dataset,
    DatasetFile,
    DatasetSpatialMetadata,
    DatasetType,
    DatasetVersion,
    File,
    FileVersion,
    IdentityAssignment,
    ManualAnnotationSession,
    MetricResult,
    ModelEvaluation,
    ModelPrediction,
    ProcessingRun,
    ProcessingRunInput,
    ProcessingRunOutput,
    Tool,
    ToolVersion,
    Track,
    User,
)
from app.cv.subject_detection import analyze_frame_detections
from app.cv.thumbnail import extract_thumbnail
from app.pipelines.video import VIDEO_EXTENSIONS, extract_frames, inspect_video, read_frame_jpeg
from app.schemas.video import FrameExtractionOut, FileVersionOut, VideoMetadataOut, VideoUploadOut

router = APIRouter(prefix="/videos", tags=["videos"])
STORAGE_BUCKET = "local"


def _storage_path(storage_key: str) -> Path:
    root = Path(settings.storage_root).resolve()
    path = (root / STORAGE_BUCKET / storage_key).resolve()
    if root not in path.parents:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Invalid storage path")
    return path


def _thumbnail_path(file_version_id: uuid.UUID) -> Path:
    root = Path(settings.storage_root).resolve()
    path = root / STORAGE_BUCKET / "thumbnails" / f"{file_version_id}.jpg"
    return path


def _write_thumbnail(file_version_id: uuid.UUID, video_path: Path) -> None:
    dest = _thumbnail_path(file_version_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = extract_thumbnail(video_path)
    dest.write_bytes(data)


async def _next_version(db: AsyncSession, file_id: uuid.UUID) -> int:
    value = await db.scalar(select(func.max(FileVersion.version_number)).where(FileVersion.file_id == file_id))
    return int(value or 0) + 1


@router.post("/upload", response_model=VideoUploadOut, status_code=status.HTTP_201_CREATED)
async def upload_video(
    experiment_id: uuid.UUID = Form(...),
    upload: UploadFile = UploadFileParameter(...),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Unsupported video format")

    logical_name = Path(upload.filename or "video").name
    existing = await db.scalar(select(File).where(
        File.experiment_id == experiment_id,
        File.logical_name == logical_name,
        File.deleted_at.is_(None),
    ))
    if existing is None:
        existing = File(
            experiment_id=experiment_id,
            file_type="video",
            logical_name=logical_name,
            is_raw=True,
            created_by=user.id,
        )
        db.add(existing)
        await db.flush()

    version_number = await _next_version(db, existing.id)
    storage_key = f"videos/{existing.id}/{version_number}{suffix}"
    destination = _storage_path(storage_key)
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    try:
        with destination.open("wb") as handle:
            while chunk := await upload.read(1024 * 1024):
                handle.write(chunk)
                digest.update(chunk)
                size += len(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    await db.execute(update(FileVersion).where(FileVersion.file_id == existing.id).values(is_current=False))
    version = FileVersion(
        file_id=existing.id,
        version_number=version_number,
        storage_bucket=STORAGE_BUCKET,
        storage_key=storage_key,
        mime_type=upload.content_type or mimetypes.guess_type(logical_name)[0],
        size_bytes=size,
        checksum_sha256=digest.hexdigest(),
        uploaded_by=user.id,
        is_current=True,
    )
    db.add(version)
    await db.flush()
    existing.current_version_id = version.id
    await db.commit()
    await db.refresh(version)
    if background_tasks is not None:
        background_tasks.add_task(_write_thumbnail, version.id, destination)
    return VideoUploadOut(file_version=FileVersionOut(
        id=version.id,
        file_id=version.file_id,
        version_number=version.version_number,
        logical_name=logical_name,
        storage_key=version.storage_key,
        mime_type=version.mime_type,
        size_bytes=version.size_bytes,
        checksum_sha256=version.checksum_sha256,
        uploaded_at=version.uploaded_at,
    ))


async def _video_file_version(db: AsyncSession, file_version_id: uuid.UUID) -> tuple[FileVersion, Path]:
    version = await get_or_404(db, FileVersion, file_version_id)
    file_ = await get_or_404(db, File, version.file_id)
    if file_.file_type != "video":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video file version not found")
    path = _storage_path(version.storage_key)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stored video is missing")
    return version, path


@router.get("/{file_version_id}/metadata", response_model=VideoMetadataOut)
async def get_video_metadata(
    file_version_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """FPS/frame count/resolution for a stored video, e.g. to size a calibration UI's frame slider."""
    _, path = await _video_file_version(db, file_version_id)
    try:
        meta = await asyncio.to_thread(inspect_video, path)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return VideoMetadataOut(
        fps=meta.fps, frame_count=meta.frame_count, width=meta.width, height=meta.height, duration_seconds=meta.duration_seconds
    )


@router.get("/{file_version_id}/frame")
async def get_video_frame(
    file_version_id: uuid.UUID,
    frame_index: int = Query(..., ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    _, path = await _video_file_version(db, file_version_id)
    try:
        jpeg_bytes = await asyncio.to_thread(read_frame_jpeg, path, frame_index)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return Response(content=jpeg_bytes, media_type="image/jpeg")


@router.get("/{file_version_id}/detection-analysis")
async def get_detection_analysis(
    file_version_id: uuid.UUID,
    frame_index: int = Query(..., ge=0),
    min_area: float = Query(50.0, gt=0),
    max_area: float = Query(250.0, gt=0),
    brightness_ratio: float = Query(0.85, gt=0, le=1),
    min_solidity: float = Query(0.80, gt=0, le=1),
    min_aspect_ratio: float = Query(0.5, gt=0),
    max_aspect_ratio: float = Query(2.0, gt=0),
    min_circularity: float = Query(0.50, gt=0, le=1),
    plate_cx: int | None = Query(None),
    plate_cy: int | None = Query(None),
    plate_r: int | None = Query(None, ge=1),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _, path = await _video_file_version(db, file_version_id)
    try:
        result = await asyncio.to_thread(
            analyze_frame_detections, path, frame_index,
            min_area, max_area, brightness_ratio,
            min_solidity, min_aspect_ratio, max_aspect_ratio, min_circularity,
            plate_cx, plate_cy, plate_r,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return result


@router.post("/{file_version_id}/extract-frames", response_model=FrameExtractionOut, status_code=status.HTTP_201_CREATED)
async def extract_video_frames(
    file_version_id: uuid.UUID,
    experiment_id: uuid.UUID = Form(...),
    fps: float = Form(..., gt=0),
    width: int | None = Form(None, gt=0),
    height: int | None = Form(None, gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    source = (await db.execute(select(FileVersion, File).join(File, File.id == FileVersion.file_id).where(
        FileVersion.id == file_version_id,
        File.experiment_id == experiment_id,
        File.file_type == "video",
    ))).first()
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video version not found")
    source_version, source_file = source
    source_path = _storage_path(source_version.storage_key)
    if not source_path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stored video is missing")

    tool = await db.scalar(select(Tool).where(Tool.name == "opencv-frame-extractor"))
    if tool is None:
        tool = Tool(name="opencv-frame-extractor", category="video-processing", description="Sequential OpenCV frame extraction")
        db.add(tool)
        await db.flush()
    tool_version = await db.scalar(select(ToolVersion).where(
        ToolVersion.tool_id == tool.id,
        ToolVersion.version_label == "1.0",
    ))
    if tool_version is None:
        tool_version = ToolVersion(tool_id=tool.id, version_label="1.0")
        db.add(tool_version)
        await db.flush()

    run = ProcessingRun(
        experiment_id=experiment_id,
        tool_version_id=tool_version.id,
        initiated_by=user.id,
        status="running",
        parameters={"fps": fps, "width": width, "height": height, "source_file_version_id": str(file_version_id)},
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()
    db.add(ProcessingRunInput(
        processing_run_id=run.id,
        artifact_type="file_version",
        file_version_id=file_version_id,
        role="source_video",
    ))
    await db.commit()

    output_dir = Path(settings.storage_root).resolve() / STORAGE_BUCKET / "frames" / str(run.id)
    try:
        result = await asyncio.to_thread(extract_frames, source_path, output_dir, fps, width, height)
        dataset_type = await db.scalar(select(DatasetType).where(DatasetType.key == "video_frames"))
        if dataset_type is None:
            dataset_type = DatasetType(key="video_frames", display_name="Extracted video frames")
            db.add(dataset_type)
            await db.flush()
        dataset = Dataset(
            experiment_id=experiment_id,
            dataset_type="video_frames",
            name=f"Frames from {source_file.logical_name}",
            description="Immutable frame sequence extracted from one video file version",
            origin="automatic",
            status="valid",
            created_by=user.id,
        )
        db.add(dataset)
        await db.flush()
        dataset_version = DatasetVersion(
            dataset_id=dataset.id,
            version_number=1,
            schema_version="video-frames-1.0",
            changelog=f"Extracted from file version {file_version_id}",
            created_by=user.id,
            is_current=True,
        )
        db.add(dataset_version)
        await db.flush()
        manifest_key = f"frames/{run.id}/manifest.json"
        manifest_file = File(
            experiment_id=experiment_id,
            file_type="json",
            logical_name=f"{source_file.logical_name}.frames.manifest.json",
            description="Manifest for an extracted frame dataset",
            is_raw=False,
            created_by=user.id,
        )
        db.add(manifest_file)
        await db.flush()
        manifest_digest = hashlib.sha256(result.manifest_path.read_bytes()).hexdigest()
        manifest_version = FileVersion(
            file_id=manifest_file.id,
            version_number=1,
            storage_bucket=STORAGE_BUCKET,
            storage_key=manifest_key,
            mime_type="application/json",
            size_bytes=result.manifest_path.stat().st_size,
            checksum_sha256=manifest_digest,
            uploaded_by=user.id,
            is_current=True,
        )
        db.add(manifest_version)
        await db.flush()
        manifest_file.current_version_id = manifest_version.id
        db.add(DatasetFile(dataset_version_id=dataset_version.id, file_version_id=manifest_version.id, role="frame_manifest"))
        db.add(DatasetSpatialMetadata(
            dataset_version_id=dataset_version.id,
            sampling_rate_hz=result.effective_fps,
            units="pixels",
            frame_start=0,
            frame_end=result.frame_count - 1,
        ))
        db.add(ProcessingRunOutput(
            processing_run_id=run.id,
            artifact_type="dataset_version",
            dataset_version_id=dataset_version.id,
            role="extracted_frames",
        ))
        run.status = "succeeded"
        run.completed_at = datetime.now(timezone.utc)
        run.runtime_info = {"source_fps": result.metadata.fps, "source_frame_count": result.metadata.frame_count}
        dataset.current_version_id = dataset_version.id
        await db.commit()
    except Exception as exc:
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error_message = str(exc)
        await db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Frame extraction failed: {exc}") from exc

    return FrameExtractionOut(
        run_id=run.id,
        dataset_version_id=dataset_version.id,
        manifest_file_version_id=manifest_version.id,
        requested_fps=result.requested_fps,
        effective_fps=result.effective_fps,
        frame_count=result.frame_count,
        source_width=result.metadata.width,
        source_height=result.metadata.height,
        source_fps=result.metadata.fps,
        source_frame_count=result.metadata.frame_count,
    )


@router.get("/{file_version_id}/thumbnail")
async def get_thumbnail(file_version_id: uuid.UUID, _: User = Depends(get_current_user)):
    path = _thumbnail_path(file_version_id)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thumbnail not generated yet")
    return FileResponse(path, media_type="image/jpeg")


@router.post("/{file_version_id}/thumbnail", status_code=status.HTTP_204_NO_CONTENT)
async def generate_thumbnail(
    file_version_id: uuid.UUID,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    version = await get_or_404(db, FileVersion, file_version_id)
    video_path = _storage_path(version.storage_key)
    if not video_path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video file not found on disk")
    await asyncio.to_thread(_write_thumbnail, file_version_id, video_path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _delete_video_cascade(db: AsyncSession, video_file: File) -> None:
    video_fv_ids: list[uuid.UUID] = list(await db.scalars(
        select(FileVersion.id).where(FileVersion.file_id == video_file.id)
    ))

    visited_run_ids: set[uuid.UUID] = set()
    all_output_fv_ids: set[uuid.UUID] = set()
    all_output_dv_ids: set[uuid.UUID] = set()

    frontier_fv: set[uuid.UUID] = set(video_fv_ids)
    frontier_dv: set[uuid.UUID] = set()

    while frontier_fv or frontier_dv:
        new_runs: set[uuid.UUID] = set()
        if frontier_fv:
            new_runs |= set(await db.scalars(
                select(ProcessingRunInput.processing_run_id)
                .where(ProcessingRunInput.file_version_id.in_(frontier_fv))
            ))
        if frontier_dv:
            new_runs |= set(await db.scalars(
                select(ProcessingRunInput.processing_run_id)
                .where(ProcessingRunInput.dataset_version_id.in_(frontier_dv))
            ))
        new_runs -= visited_run_ids
        if not new_runs:
            break
        visited_run_ids |= new_runs
        frontier_fv = set()
        frontier_dv = set()
        for row in await db.execute(
            select(ProcessingRunOutput.file_version_id, ProcessingRunOutput.dataset_version_id)
            .where(ProcessingRunOutput.processing_run_id.in_(new_runs))
        ):
            if row.file_version_id:
                frontier_fv.add(row.file_version_id)
                all_output_fv_ids.add(row.file_version_id)
            if row.dataset_version_id:
                frontier_dv.add(row.dataset_version_id)
                all_output_dv_ids.add(row.dataset_version_id)

    derived_file_ids: set[uuid.UUID] = set()
    if all_output_fv_ids:
        derived_file_ids = set(await db.scalars(
            select(FileVersion.file_id).where(FileVersion.id.in_(all_output_fv_ids))
        ))

    derived_dataset_ids: set[uuid.UUID] = set()
    if all_output_dv_ids:
        derived_dataset_ids = set(await db.scalars(
            select(DatasetVersion.dataset_id).where(DatasetVersion.id.in_(all_output_dv_ids))
        ))

    all_storage_keys: list[str] = list(await db.scalars(
        select(FileVersion.storage_key).where(FileVersion.file_id == video_file.id)
    ))
    if all_output_fv_ids:
        all_storage_keys.extend(await db.scalars(
            select(FileVersion.storage_key).where(FileVersion.id.in_(all_output_fv_ids))
        ))

    if visited_run_ids:
        comp_run_ids = list(await db.scalars(
            select(ComparisonRun.id).where(ComparisonRun.processing_run_id.in_(visited_run_ids))
        ))
        if comp_run_ids:
            await db.execute(sa_delete(ComparisonResult).where(ComparisonResult.comparison_run_id.in_(comp_run_ids)))
        await db.execute(sa_delete(ComparisonRun).where(ComparisonRun.processing_run_id.in_(visited_run_ids)))
        await db.execute(sa_delete(MetricResult).where(MetricResult.processing_run_id.in_(visited_run_ids)))
        await db.execute(sa_delete(ModelEvaluation).where(ModelEvaluation.processing_run_id.in_(visited_run_ids)))
        await db.execute(sa_delete(ModelPrediction).where(ModelPrediction.processing_run_id.in_(visited_run_ids)))
        await db.execute(sa_delete(IdentityAssignment).where(IdentityAssignment.assigned_by_run.in_(visited_run_ids)))
        track_ids = list(await db.scalars(
            select(Track.id).where(Track.processing_run_id.in_(visited_run_ids))
        ))
        if track_ids:
            await db.execute(sa_delete(IdentityAssignment).where(IdentityAssignment.track_id.in_(track_ids)))
        await db.execute(sa_delete(Track).where(Track.processing_run_id.in_(visited_run_ids)))

    all_affected_fv_ids = set(video_fv_ids) | all_output_fv_ids
    if all_affected_fv_ids:
        session_ids = list(await db.scalars(
            select(ManualAnnotationSession.id)
            .where(ManualAnnotationSession.source_file_version_id.in_(all_affected_fv_ids))
        ))
        if session_ids:
            await db.execute(sa_delete(AnnotationPoint).where(AnnotationPoint.session_id.in_(session_ids)))
            await db.execute(sa_delete(ManualAnnotationSession).where(ManualAnnotationSession.id.in_(session_ids)))

    if visited_run_ids:
        await db.execute(sa_delete(ProcessingRunInput).where(ProcessingRunInput.processing_run_id.in_(visited_run_ids)))
        await db.execute(sa_delete(ProcessingRunOutput).where(ProcessingRunOutput.processing_run_id.in_(visited_run_ids)))
        await db.execute(sa_delete(ProcessingRun).where(ProcessingRun.id.in_(visited_run_ids)))

    if all_output_dv_ids:
        await db.execute(sa_delete(DatasetSpatialMetadata).where(DatasetSpatialMetadata.dataset_version_id.in_(all_output_dv_ids)))
        await db.execute(sa_delete(DatasetFile).where(DatasetFile.dataset_version_id.in_(all_output_dv_ids)))
    if all_output_fv_ids:
        await db.execute(sa_delete(DatasetFile).where(DatasetFile.file_version_id.in_(all_output_fv_ids)))
    if derived_dataset_ids:
        await db.execute(update(Dataset).where(Dataset.id.in_(derived_dataset_ids)).values(current_version_id=None))
    if all_output_dv_ids:
        await db.execute(sa_delete(DatasetVersion).where(DatasetVersion.id.in_(all_output_dv_ids)))
    if derived_dataset_ids:
        await db.execute(sa_delete(Dataset).where(Dataset.id.in_(derived_dataset_ids)))

    if derived_file_ids:
        await db.execute(update(File).where(File.id.in_(derived_file_ids)).values(current_version_id=None))
    if all_output_fv_ids:
        await db.execute(sa_delete(FileVersion).where(FileVersion.id.in_(all_output_fv_ids)))
    if derived_file_ids:
        await db.execute(sa_delete(File).where(File.id.in_(derived_file_ids)))

    await db.execute(update(File).where(File.id == video_file.id).values(current_version_id=None))
    await db.execute(sa_delete(FileVersion).where(FileVersion.file_id == video_file.id))
    await db.execute(sa_delete(File).where(File.id == video_file.id))

    await db.commit()

    storage_root = Path(settings.storage_root).resolve()
    for key in all_storage_keys:
        path = (storage_root / "local" / key).resolve()
        if storage_root in path.parents:
            path.unlink(missing_ok=True)
    for fv_id in video_fv_ids:
        _thumbnail_path(fv_id).unlink(missing_ok=True)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_video(
    file_id: uuid.UUID,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    file_ = await db.scalar(
        select(File).where(File.id == file_id, File.file_type == "video", File.deleted_at.is_(None))
    )
    if file_ is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found")
    await _delete_video_cascade(db, file_)