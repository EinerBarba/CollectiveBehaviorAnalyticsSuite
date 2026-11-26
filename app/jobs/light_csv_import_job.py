"""Background job that imports light-stimulus positions from CSV files.

Lets light positions tracked elsewhere replace Step 1. Each CSV is matched to
a video by file name. The circle's center and radius, the light's angles and
its angular velocity are all derived from the positions, and the result is
recorded as if a light-tracking run had produced it. See
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

import cv2
from sqlalchemy import select

from app import storage
from app.crud.base import get_or_create
from app.cv.manual_tracking import trajectory_csv_bytes
from app.database import AsyncSessionLocal
from app.models import (
    Dataset,
    DatasetFile,
    DatasetSpatialMetadata,
    DatasetType,
    DatasetVersion,
    File,
    FileVersion,
    MetricDefinition,
    MetricResult,
    ProcessingRun,
    ProcessingRunInput,
    ProcessingRunOutput,
    Tool,
    ToolVersion,
    Track,
)

TOOL_NAME = "Light CSV Import"
"""Tool name of the overall import run."""

TOOL_VERSION_LABEL = "1.0.0"
"""Tool version of the overall import run."""

_TRAJ_TOOL_NAME = "Manual Circular Trajectory"
_TRAJ_TV_LABEL = "csv-import-1.0.0"


def _read_video_info(video_path: str) -> tuple[float, int]:
    """Return a video's frame rate and frame count, raising ValueError if either is missing."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {Path(video_path).name}")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:
        cap.release()
    if fps <= 0 or frame_count <= 0:
        raise ValueError(f"Invalid FPS or frame count in video: {Path(video_path).name}")
    return fps, frame_count


def _parse_light_csv(content: bytes) -> list[tuple[int, float | None, float | None]]:
    """Read a light CSV with the columns `frame`, `x` and `y`.

    A position of (-1, -1) means the light was off or not visible.

    Returns:
        (frame, x, y) per row, with x and y None where the light is absent.

    Raises:
        ValueError: If the file has no rows. A missing column or unreadable
            number raises KeyError or ValueError.
    """
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[tuple[int, float | None, float | None]] = []
    for row in reader:
        frame = int(float(row["frame"]))
        x = float(row["x"])
        y = float(row["y"])
        if x == -1.0 and y == -1.0:
            rows.append((frame, None, None))
        else:
            rows.append((frame, x, y))
    if not rows:
        raise ValueError("Light CSV is empty")
    return rows


def _compute_center_radius(rows: list[tuple[int, float | None, float | None]]) -> tuple[float, float, float]:
    """Estimate the light's circle from the extremes of its positions.

    The center is the middle of the positions' bounding box, and the radius
    is the mean of its half-width and half-height. This is accurate only if
    the light covers the whole circle at least once.

    Returns:
        Center x, center y and radius, in pixels.

    Raises:
        ValueError: If no frame has a light position.
    """
    valid_xs = [x for _, x, _ in rows if x is not None]
    valid_ys = [y for _, _, y in rows if y is not None]
    if not valid_xs:
        raise ValueError("No valid light positions in CSV (all frames are -1,-1)")
    cx = (min(valid_xs) + max(valid_xs)) / 2.0
    cy = (min(valid_ys) + max(valid_ys)) / 2.0
    rx = (max(valid_xs) - min(valid_xs)) / 2.0
    ry = (max(valid_ys) - min(valid_ys)) / 2.0
    return cx, cy, (rx + ry) / 2.0


def _build_trajectory(
    rows: list[tuple[int, float | None, float | None]],
    cx: float,
    cy: float,
    fps: float,
    source_frames: int,
) -> list[dict]:
    """Build a full light trajectory from the imported positions.

    For each frame with a position, `theta_rad` is the light's angle around
    the center, from -π to π. `unwrapped_angle_rad` is that angle made
    continuous, by taking the shortest turn between consecutive positions.
    `instantaneous_omega_rad_s` is the rate of change of the unwrapped angle,
    from the neighboring positions on either side (one side at the ends).
    Frames without a position get (-1, -1) and zero angles.

    Note that `theta_rad` is wrapped here but unwrapped in trajectories from
    `generate_manual_trajectory`.

    Returns:
        One row per frame from 0 to `source_frames` − 1, in the same format as
        `generate_manual_trajectory`.
    """
    frame_map: dict[int, tuple[float, float]] = {
        f: (x, y) for f, x, y in rows if x is not None
    }
    valid_frames = sorted(frame_map.keys())

    thetas: dict[int, float] = {
        f: math.atan2(frame_map[f][1] - cy, frame_map[f][0] - cx)
        for f in valid_frames
    }

    unwrapped: dict[int, float] = {}
    if valid_frames:
        unwrapped[valid_frames[0]] = thetas[valid_frames[0]]
        for i in range(1, len(valid_frames)):
            f = valid_frames[i]
            prev_f = valid_frames[i - 1]
            delta = thetas[f] - thetas[prev_f]
            delta = (delta + math.pi) % (2.0 * math.pi) - math.pi
            unwrapped[f] = unwrapped[prev_f] + delta

    omegas: dict[int, float] = {}
    n = len(valid_frames)
    for i, f in enumerate(valid_frames):
        if n == 1:
            omegas[f] = 0.0
        elif i == 0:
            nf = valid_frames[1]
            dt = (nf - f) / fps
            omegas[f] = (unwrapped[nf] - unwrapped[f]) / dt if dt > 0 else 0.0
        elif i == n - 1:
            pf = valid_frames[i - 1]
            dt = (f - pf) / fps
            omegas[f] = (unwrapped[f] - unwrapped[pf]) / dt if dt > 0 else 0.0
        else:
            pf = valid_frames[i - 1]
            nf = valid_frames[i + 1]
            dt = (nf - pf) / fps
            omegas[f] = (unwrapped[nf] - unwrapped[pf]) / dt if dt > 0 else 0.0

    trajectory = []
    for frame in range(source_frames):
        ts = round(frame / fps * 1000, 3)
        if frame in frame_map:
            x_px, y_px = frame_map[frame]
            trajectory.append({
                "frame": frame,
                "timestamp_ms": ts,
                "x": x_px,
                "y": y_px,
                "theta_rad": thetas[frame],
                "unwrapped_angle_rad": unwrapped.get(frame, 0.0),
                "instantaneous_omega_rad_s": omegas.get(frame, 0.0),
            })
        else:
            trajectory.append({
                "frame": frame,
                "timestamp_ms": ts,
                "x": -1.0,
                "y": -1.0,
                "theta_rad": 0.0,
                "unwrapped_angle_rad": 0.0,
                "instantaneous_omega_rad_s": 0.0,
            })
    return trajectory


async def _process_one(
    db,
    filename: str,
    content: bytes,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID,
    fps_override: float | None,
    video_by_stem: dict[str, File],
    now: datetime,
) -> dict:
    """Import one light CSV.

    The CSV's name, without extension and ignoring case, must match a video
    in the experiment. With `fps_override`, the trajectory covers the
    frames in the CSV and that frame rate is used; otherwise it covers the
    whole video at the video's own rate.

    The stand-in light-tracking run stores the derived center and radius in
    its parameters, with `csv_import: True`, and summary values in its
    `runtime_info`. The mean angular velocity is the average of the
    per-frame values, and the rotation period is derived from it.

    Returns:
        Frame count, number of frames with a light position, and the center
        and radius, rounded to two decimals.

    Raises:
        ValueError: If no video matches, the video cannot be read, or the
            CSV has no light positions.
    """
    stem = Path(filename).stem.lower()
    video_file = video_by_stem.get(stem)
    if not video_file:
        raise ValueError(f"No video named '{Path(filename).stem}' in this experiment")

    video_fv = await db.get(FileVersion, video_file.current_version_id)
    video_path = str(storage.full_path(video_fv.storage_key))
    native_fps, native_frames = await asyncio.to_thread(_read_video_info, video_path)
    fps = fps_override if fps_override is not None else native_fps

    rows = _parse_light_csv(content)
    cx, cy, radius = _compute_center_radius(rows)

    if fps_override is not None:
        all_csv_frames = [f for f, _, _ in rows]
        source_frames = (max(all_csv_frames) + 1) if all_csv_frames else native_frames
    else:
        source_frames = native_frames

    trajectory = _build_trajectory(rows, cx, cy, fps, source_frames)

    subdir = f"experiments/{experiment_id}/csv-imports"
    traj_bytes = trajectory_csv_bytes(trajectory)
    csv_key, checksum, size = storage.save_bytes(traj_bytes, subdir, f"light_trajectory_{stem}.csv")

    traj_file = File(
        experiment_id=experiment_id,
        file_type="csv",
        logical_name=f"light_trajectory_{stem}.csv",
        is_raw=False,
        created_by=user_id,
    )
    db.add(traj_file)
    await db.flush()
    traj_fv = FileVersion(
        file_id=traj_file.id,
        version_number=1,
        storage_bucket=storage.STORAGE_BUCKET,
        storage_key=csv_key,
        mime_type="text/csv",
        size_bytes=size,
        checksum_sha256=checksum,
        uploaded_by=user_id,
        is_current=True,
    )
    db.add(traj_fv)
    await db.flush()
    traj_file.current_version_id = traj_fv.id

    valid_rows = [(f, x, y) for f, x, y in rows if x is not None]
    frame_start = valid_rows[0][0] if valid_rows else 0
    frame_end = valid_rows[-1][0] if valid_rows else source_frames - 1

    await get_or_create(
        db, DatasetType, key="trajectory_positions",
        defaults={"display_name": "Trajectory Positions"},
    )
    ds = Dataset(
        experiment_id=experiment_id,
        dataset_type="trajectory_positions",
        name=f"Light trajectory – CSV import – {Path(filename).stem}",
        origin="automatic",
        status="valid",
        created_by=user_id,
    )
    db.add(ds)
    await db.flush()
    dv = DatasetVersion(
        dataset_id=ds.id,
        version_number=1,
        schema_version="trajectory-positions-1.0",
        changelog="Imported from external light position CSV",
        created_by=user_id,
        is_current=True,
    )
    db.add(dv)
    await db.flush()
    ds.current_version_id = dv.id
    db.add(DatasetFile(dataset_version_id=dv.id, file_version_id=traj_fv.id, role="primary"))
    db.add(DatasetSpatialMetadata(
        dataset_version_id=dv.id,
        coordinate_system="pixel",
        sampling_rate_hz=fps,
        units="px",
        frame_start=frame_start,
        frame_end=frame_end,
    ))

    traj_valid = [t for t in trajectory if t["x"] != -1.0]
    if len(traj_valid) >= 2:
        omegas_list = [t["instantaneous_omega_rad_s"] for t in traj_valid]
        avg_omega = sum(omegas_list) / len(omegas_list)
        ang_disp = traj_valid[-1]["unwrapped_angle_rad"] - traj_valid[0]["unwrapped_angle_rad"]
        rot_period_s = abs(2.0 * math.pi / avg_omega) if avg_omega != 0.0 else None
        rev_count = abs(ang_disp) / (2.0 * math.pi)
    else:
        avg_omega = 0.0
        ang_disp = 0.0
        rot_period_s = None
        rev_count = 0.0

    metrics = {
        "source_fps": fps,
        "source_frame_count": source_frames,
        "duration_seconds": source_frames / fps,
        "angular_velocity_rad_s": avg_omega,
        "angular_velocity_deg_s": math.degrees(avg_omega),
        "angular_displacement_rad": ang_disp,
        "revolution_count": rev_count,
        **({"rotation_period_s": rot_period_s} if rot_period_s is not None else {}),
    }

    traj_tool = await get_or_create(
        db, Tool, name=_TRAJ_TOOL_NAME,
        defaults={"category": "video-processing", "description": "Manual circular trajectory generation"},
    )
    traj_tv = await get_or_create(db, ToolVersion, tool_id=traj_tool.id, version_label=_TRAJ_TV_LABEL)
    traj_run = ProcessingRun(
        experiment_id=experiment_id,
        tool_version_id=traj_tv.id,
        initiated_by=user_id,
        status="succeeded",
        started_at=now,
        completed_at=now,
        parameters={
            "source_file_version_id": str(video_fv.id),
            "center_x": cx,
            "center_y": cy,
            "radius_px": radius,
            "csv_import": True,
        },
        runtime_info=metrics,
    )
    db.add(traj_run)
    await db.flush()
    db.add(ProcessingRunInput(
        processing_run_id=traj_run.id,
        artifact_type="file_version",
        file_version_id=video_fv.id,
        role="raw_video",
    ))
    db.add(ProcessingRunOutput(
        processing_run_id=traj_run.id,
        artifact_type="dataset_version",
        dataset_version_id=dv.id,
        role="primary_output",
    ))
    db.add(Track(
        dataset_version_id=dv.id,
        processing_run_id=traj_run.id,
        track_label="csv_import_light_trajectory",
        start_frame=frame_start,
        end_frame=frame_end,
    ))

    definitions = {
        "trajectory_center_x": ("Trajectory Center X", "px"),
        "trajectory_center_y": ("Trajectory Center Y", "px"),
        "trajectory_radius_px": ("Trajectory Radius", "px"),
        "rotation_period_s": ("Rotation Period", "s"),
        "angular_velocity_rad_s": ("Angular Velocity", "rad/s"),
        "angular_velocity_deg_s": ("Angular Velocity", "deg/s"),
        "angular_displacement_rad": ("Angular Displacement", "rad"),
        "revolution_count": ("Revolution Count", "rev"),
    }
    values = {
        "trajectory_center_x": cx,
        "trajectory_center_y": cy,
        "trajectory_radius_px": radius,
        **{k: metrics[k] for k in definitions if k in metrics},
    }
    for key, (display_name, unit) in definitions.items():
        await get_or_create(
            db, MetricDefinition, key=key,
            defaults={"display_name": display_name, "unit": unit, "value_type": "scalar", "scope": "individual"},
        )
        if key in values:
            db.add(MetricResult(
                dataset_version_id=dv.id,
                processing_run_id=traj_run.id,
                metric_key=key,
                value_numeric=values[key],
            ))

    return {
        "n_frames": source_frames,
        "n_valid_light_frames": len(valid_rows),
        "center_x": round(cx, 2),
        "center_y": round(cy, 2),
        "radius_px": round(radius, 2),
    }


async def run_light_csv_import_job(
    import_run_id: uuid.UUID,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID,
    fps_override: float | None,
    file_data: dict[str, bytes],
) -> None:
    """Import several light CSVs.

    Each file is processed on its own; one failing does not stop the rest.
    The overall run succeeds if at least one file was imported, and its
    `runtime_info` lists the outcome per file.

    Args:
        import_run_id: The overall import run, in status `queued`.
        experiment_id: The experiment to import into.
        user_id: The user who started the import.
        fps_override: Frame rate of the CSV rows. None uses each video's own.
        file_data: File contents keyed by file name.
    """
    async with AsyncSessionLocal() as db:
        master = await db.get(ProcessingRun, import_run_id)
        master.status = "running"
        master.started_at = datetime.now(timezone.utc)
        await db.commit()

    results: dict[str, dict] = {}
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
                    info = await _process_one(db, filename, content, experiment_id, user_id, fps_override, video_by_stem, now)
                    results[filename] = {"success": True, **info}
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
