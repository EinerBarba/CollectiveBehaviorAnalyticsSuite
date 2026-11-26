"""Background job that imports subject positions from CSV files.

Lets positions tracked elsewhere skip Steps 2 and 3. Each CSV is matched to
a video of the experiment by file name, and its positions become a detections
file and a trajectory file, recorded as if detection and tracking had run.
A kinematics run is then started for each imported trajectory. See
[Data import](../pipeline/import.md).
"""

from __future__ import annotations

import asyncio
import csv
import io
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app import storage
from app.crud.base import get_or_create
from app.database import AsyncSessionLocal
from app.jobs.subject_kinematics_job import run_subject_kinematics_job
from app.models import (
    Dataset,
    DatasetFile,
    DatasetSpatialMetadata,
    DatasetType,
    DatasetVersion,
    File,
    FileVersion,
    ProcessingRun,
    ProcessingRunInput,
    ProcessingRunOutput,
    Tool,
    ToolVersion,
    Track,
)
from app.tracking.io import detections_to_json_bytes, trajectories_to_csv_bytes
from app.tracking.positional_tracker import TrackPoint

TOOL_NAME = "Position CSV Import"
"""Tool name of the overall import run."""

TOOL_VERSION_LABEL = "1.0.0"
"""Tool version of the overall import run."""

_DET_TOOL_NAME = "Subject Detector"
_DET_TV_LABEL = "csv-import-1.0.0"
_TRACK_TOOL_NAME = "Positional Tracker"
_TRACK_TV_LABEL = "csv-import-1.0.0"
_KIN_TOOL_NAME = "Subject Kinematics"
_KIN_TV_LABEL = "1.0.0"


def _safe_float(v: str) -> float | None:
    """Parse a cell as a number, returning None for blanks, NaN and spreadsheet error values."""
    v = v.strip()
    if not v or v.lower() in ("nan", "na", "none", "null", "#n/a", "#value!"):
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except ValueError:
        return None


def _parse_csv(content: bytes) -> tuple[list[list[float | None]], int]:
    """Read a position CSV into rows of numbers.

    The expected layout is one row per frame and two columns per subject:
    x1, y1, x2, y2, and so on. A first row with no numbers is treated as a
    header and skipped. Blank rows are skipped.

    Returns:
        The rows, with None for missing values, and the number of subjects
        (half the widest row's column count).

    Raises:
        ValueError: If the file is empty or has fewer than two columns.
    """
    text = content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows: list[list[float | None]] = []
    first_row_done = False
    for row in reader:
        if not row:
            continue
        parsed = [_safe_float(v) for v in row]
        if not first_row_done:
            first_row_done = True
            if not any(v is not None for v in parsed):
                continue
        rows.append(parsed)
    if not rows:
        raise ValueError("CSV is empty")
    n_cols = max(len(r) for r in rows)
    if n_cols < 2:
        raise ValueError("CSV must have at least 2 columns (one x,y pair per subject)")
    return rows, n_cols // 2


def _build_outputs(
    rows: list[list[float | None]],
    n_subjects: int,
    arena_cx: float,
    arena_cy: float,
) -> tuple[dict[int, list[tuple[float, float]]], dict[int, list[TrackPoint]]]:
    """Turn parsed rows into detections and tracks.

    CSV coordinates are taken as offsets from the arena center, so the
    center is added to every value to get pixel positions. Row number
    becomes the frame number, starting at 0. A subject with a missing x or y
    in a row is left out of that frame.

    Returns:
        Detections per frame, and one track per subject (keyed from 0),
        leaving out subjects with no positions at all.
    """
    detection_frames: dict[int, list[tuple[float, float]]] = {}
    subject_tracks: dict[int, list[TrackPoint]] = {i: [] for i in range(n_subjects)}
    for frame_idx, row in enumerate(rows):
        frame_dets: list[tuple[float, float]] = []
        for s in range(n_subjects):
            xi, yi = s * 2, s * 2 + 1
            xv = row[xi] if xi < len(row) else None
            yv = row[yi] if yi < len(row) else None
            if xv is None or yv is None:
                continue
            px, py = arena_cx + xv, arena_cy + yv
            frame_dets.append((px, py))
            subject_tracks[s].append(TrackPoint(frame_idx, px, py, False))
        if frame_dets:
            detection_frames[frame_idx] = frame_dets
    tracks = {s: pts for s, pts in subject_tracks.items() if pts}
    return detection_frames, tracks


async def _save_file_version(
    db,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID,
    data: bytes,
    file_type: str,
    logical_name: str,
    mime_type: str,
    storage_subdir: str,
    storage_filename: str,
) -> tuple[File, FileVersion]:
    """Save bytes to storage and register them as a new file with one version."""
    key, checksum, size = storage.save_bytes(data, storage_subdir, storage_filename)
    f = File(
        experiment_id=experiment_id,
        file_type=file_type,
        logical_name=logical_name,
        is_raw=False,
        created_by=user_id,
    )
    db.add(f)
    await db.flush()
    fv = FileVersion(
        file_id=f.id,
        version_number=1,
        storage_bucket=storage.STORAGE_BUCKET,
        storage_key=key,
        mime_type=mime_type,
        size_bytes=size,
        checksum_sha256=checksum,
        uploaded_by=user_id,
        is_current=True,
    )
    db.add(fv)
    await db.flush()
    f.current_version_id = fv.id
    return f, fv


async def _make_dataset_version(
    db,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID,
    type_key: str,
    type_display: str,
    dataset_name: str,
    schema_ver: str,
    fv: FileVersion,
    fps: float | None,
    frame_start: int | None,
    frame_end: int | None,
) -> DatasetVersion:
    """Create a dataset with one version holding `fv` as its primary file, plus its spatial metadata."""
    await get_or_create(db, DatasetType, key=type_key, defaults={"display_name": type_display})
    ds = Dataset(
        experiment_id=experiment_id,
        dataset_type=type_key,
        name=dataset_name,
        origin="automatic",
        status="valid",
        created_by=user_id,
    )
    db.add(ds)
    await db.flush()
    dv = DatasetVersion(
        dataset_id=ds.id,
        version_number=1,
        schema_version=schema_ver,
        changelog="Imported from external position CSV",
        created_by=user_id,
        is_current=True,
    )
    db.add(dv)
    await db.flush()
    ds.current_version_id = dv.id
    db.add(DatasetFile(dataset_version_id=dv.id, file_version_id=fv.id, role="primary"))
    db.add(DatasetSpatialMetadata(
        dataset_version_id=dv.id,
        coordinate_system="pixel",
        sampling_rate_hz=fps,
        units="px",
        frame_start=frame_start,
        frame_end=frame_end,
    ))
    return dv


async def _make_synthetic_run(
    db,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID,
    tool_name: str,
    tv_label: str,
    tool_category: str,
    tool_desc: str,
    params: dict,
    runtime_info: dict,
    now: datetime,
    input_fv: FileVersion,
    input_role: str,
    out_dv: DatasetVersion,
) -> ProcessingRun:
    """Record an already-finished run that stands in for a pipeline step.

    Imported data gets the same records a real detection or tracking run
    would leave, under the same tool name but with a `csv-import` version
    label, so later steps find it the same way.

    Returns:
        The new run, with status `succeeded`.
    """
    tool = await get_or_create(db, Tool, name=tool_name, defaults={"category": tool_category, "description": tool_desc})
    tv = await get_or_create(db, ToolVersion, tool_id=tool.id, version_label=tv_label)
    run = ProcessingRun(
        experiment_id=experiment_id,
        tool_version_id=tv.id,
        initiated_by=user_id,
        status="succeeded",
        started_at=now,
        completed_at=now,
        parameters=params,
        runtime_info=runtime_info,
    )
    db.add(run)
    await db.flush()
    db.add(ProcessingRunInput(
        processing_run_id=run.id, artifact_type="file_version",
        file_version_id=input_fv.id, role=input_role,
    ))
    db.add(ProcessingRunOutput(
        processing_run_id=run.id, artifact_type="dataset_version",
        dataset_version_id=out_dv.id, role="primary_output",
    ))
    return run


async def _process_one(
    db,
    filename: str,
    content: bytes,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID,
    fps: float | None,
    video_by_stem: dict[str, File],
    now: datetime,
) -> dict:
    """Import one position CSV.

    The CSV's name, without extension and ignoring case, must match a video
    in the experiment. That video must already have a succeeded light
    tracking run, whose center is used as the arena center.

    The function stores a detections file and a trajectory file, each in its
    own dataset; records a stand-in detection run and tracking run; stores
    one `Track` row per subject; and creates a queued kinematics run. The
    kinematics job itself is started by the caller after everything is
    committed.

    Returns:
        `n_subjects`, `n_frames`, the kinematics run's ID (`kin_run_id`) and
        the trajectory file version's ID (`traj_fv_id`).

    Raises:
        ValueError: If no video matches, the video has no light tracking run,
            or the CSV holds no usable positions.
    """
    stem = Path(filename).stem.lower()
    video_file = video_by_stem.get(stem)
    if not video_file:
        raise ValueError(f"No video named '{Path(filename).stem}' in this experiment")

    video_fv = await db.get(FileVersion, video_file.current_version_id)

    light_stmt = (
        select(ProcessingRun)
        .join(ToolVersion, ProcessingRun.tool_version_id == ToolVersion.id)
        .join(Tool, ToolVersion.tool_id == Tool.id)
        .where(
            ProcessingRun.experiment_id == experiment_id,
            ProcessingRun.status == "succeeded",
            Tool.name == "Manual Circular Trajectory",
            ProcessingRun.parameters["source_file_version_id"].astext == str(video_file.current_version_id),
        )
        .order_by(ProcessingRun.created_at.desc())
        .limit(1)
    )
    light_run = (await db.execute(light_stmt)).scalar_one_or_none()
    if not light_run:
        raise ValueError(f"No light tracking run found for '{Path(filename).stem}'")

    arena_cx = float(light_run.parameters["center_x"])
    arena_cy = float(light_run.parameters["center_y"])

    rows, n_subjects = _parse_csv(content)
    detection_frames, tracks = _build_outputs(rows, n_subjects, arena_cx, arena_cy)
    if not tracks:
        raise ValueError(f"No valid position data in '{filename}'")

    subdir = f"experiments/{experiment_id}/csv-imports"
    all_frames = sorted({p.frame for pts in tracks.values() for p in pts})

    _, det_fv = await _save_file_version(
        db, experiment_id, user_id,
        detections_to_json_bytes(detection_frames),
        "json", "detections.json", "application/json",
        subdir, "detections.json",
    )

    _, track_fv = await _save_file_version(
        db, experiment_id, user_id,
        trajectories_to_csv_bytes(tracks, fps),
        "csv", "positional_tracks.csv", "text/csv",
        subdir, "positional_tracks.csv",
    )

    det_dv = await _make_dataset_version(
        db, experiment_id, user_id,
        "subject_detections", "Subject Detections",
        f"Detections – CSV import – {Path(filename).stem}",
        "subject-detections-1.0",
        det_fv, fps,
        min(detection_frames) if detection_frames else None,
        max(detection_frames) if detection_frames else None,
    )

    track_dv = await _make_dataset_version(
        db, experiment_id, user_id,
        "trajectory_positions", "Trajectory Positions",
        f"Positional tracks – CSV import – {Path(filename).stem}",
        "positional-tracks-1.0",
        track_fv, fps,
        min(all_frames) if all_frames else None,
        max(all_frames) if all_frames else None,
    )

    await _make_synthetic_run(
        db, experiment_id, user_id,
        _DET_TOOL_NAME, _DET_TV_LABEL,
        "video-processing", "Bright-spot subject detection inside the arena",
        {"source_file_version_id": str(video_fv.id), "csv_import": True},
        {"detections_file_version_id": str(det_fv.id), "fps": fps, "frame_count": len(rows)},
        now, video_fv, "raw_video", det_dv,
    )

    track_run = await _make_synthetic_run(
        db, experiment_id, user_id,
        _TRACK_TOOL_NAME, _TRACK_TV_LABEL,
        "tracking", "Positional multi-object tracking of stored detections",
        {"source_file_version_id": str(video_fv.id), "csv_import": True},
        {"track_count": len(tracks), "fps": fps},
        now, video_fv, "raw_video", track_dv,
    )

    for tid, pts in tracks.items():
        db.add(Track(
            dataset_version_id=track_dv.id,
            processing_run_id=track_run.id,
            track_label=str(tid),
            start_frame=pts[0].frame,
            end_frame=pts[-1].frame,
        ))

    kin_tool = await get_or_create(
        db, Tool, name=_KIN_TOOL_NAME,
        defaults={"category": "tracking", "description": "Per-subject displacement, speed, acceleration and heading"},
    )
    kin_tv = await get_or_create(db, ToolVersion, tool_id=kin_tool.id, version_label=_KIN_TV_LABEL)
    kin_run = ProcessingRun(
        experiment_id=experiment_id,
        tool_version_id=kin_tv.id,
        initiated_by=user_id,
        status="queued",
        parameters={
            "fps": fps,
            "trajectory_file_version_id": str(track_fv.id),
            "video_file_version_id": str(video_fv.id),
        },
    )
    db.add(kin_run)
    await db.flush()

    return {
        "n_subjects": len(tracks),
        "n_frames": len(rows),
        "kin_run_id": kin_run.id,
        "traj_fv_id": track_fv.id,
    }


async def run_csv_import_job(
    import_run_id: uuid.UUID,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID,
    fps: float | None,
    file_data: dict[str, bytes],
) -> None:
    """Import several position CSVs, then start kinematics for each.

    Each file is processed on its own; one failing does not stop the rest.
    The overall run succeeds if at least one file was imported. Its
    `runtime_info` lists, per file, either the subject and frame counts or
    the error.

    Args:
        import_run_id: The overall import run, in status `queued`.
        experiment_id: The experiment to import into.
        user_id: The user who started the import.
        fps: Frame rate of the CSV rows, used for timestamps and kinematics
            units. None leaves timestamps empty and measures time in frames.
        file_data: File contents keyed by file name.
    """
    async with AsyncSessionLocal() as db:
        master = await db.get(ProcessingRun, import_run_id)
        master.status = "running"
        master.started_at = datetime.now(timezone.utc)
        await db.commit()

    results: dict[str, dict] = {}
    kinematics_jobs: list[tuple] = []
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        try:
            video_stmt = select(File).where(
                File.experiment_id == experiment_id,
                File.file_type == "video",
                File.current_version_id.isnot(None),
            )
            videos = list((await db.execute(video_stmt)).scalars().all())
            video_by_stem: dict[str, File] = {Path(v.logical_name).stem.lower(): v for v in videos}

            for filename, content in file_data.items():
                try:
                    info = await _process_one(db, filename, content, experiment_id, user_id, fps, video_by_stem, now)
                    results[filename] = {"success": True, "n_subjects": info["n_subjects"], "n_frames": info["n_frames"]}
                    kinematics_jobs.append((info["kin_run_id"], info["traj_fv_id"], experiment_id, user_id, fps))
                except Exception as exc:
                    results[filename] = {"error": str(exc)}

            n_ok = sum(1 for r in results.values() if r.get("success"))
            n_fail = len(results) - n_ok
            master = await db.get(ProcessingRun, import_run_id)
            master.status = "succeeded" if n_ok > 0 or not results else "failed"
            if n_fail > 0 and n_ok == 0:
                master.error_message = "; ".join(r["error"] for r in results.values() if "error" in r)[:2000]
            master.completed_at = datetime.now(timezone.utc)
            master.runtime_info = {"n_processed": n_ok, "n_failed": n_fail, "results": results}
            await db.commit()
        except Exception as exc:
            await db.rollback()
            async with AsyncSessionLocal() as db2:
                master2 = await db2.get(ProcessingRun, import_run_id)
                master2.status = "failed"
                master2.error_message = str(exc)[:2000]
                master2.completed_at = datetime.now(timezone.utc)
                await db2.commit()
            return

    for params in kinematics_jobs:
        asyncio.create_task(run_subject_kinematics_job(*params))
