"""Background job for Step 3, the automatic part of Subject Tracking.

Links stored detections into tracks with `track_detections_detailed` and
stores them as a trajectory CSV in a new `trajectory_positions` dataset. The
researcher's corrections are saved later, as new versions of that CSV, by the
trajectory editor's endpoints. See [Subject tracking](../pipeline/tracking.md).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import cv2

from app import storage
from app.crud.base import get_or_create
from app.database import AsyncSessionLocal
from app.progress import set_progress, clear_progress
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
    Track,
)
from app.tracking.io import parse_detections, trajectories_to_csv_bytes
from app.tracking.positional_tracker import track_detections_detailed

TOOL_NAME = "Positional Tracker"
"""Tool name recorded on the run. The experiment-level analysis finds tracking runs by this name."""

TOOL_VERSION_LABEL = "1.0.0"
"""Tool version recorded on the run."""

DATASET_TYPE_KEY = "trajectory_positions"
"""Dataset type of the output."""


def _video_fps(video_path: str) -> float | None:
    """Read a video's frame rate, or None if it reports none."""
    capture = cv2.VideoCapture(video_path)
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
    finally:
        capture.release()
    return fps if fps and fps > 0 else None


def _track_from_artifact(
    detections_path, video_path: str, params: dict,
    on_progress=None,
) -> tuple[dict, float | None]:
    """Load detections, track them, and work out the frame rate.

    Runs in a worker thread.

    Returns:
        The tracks, and the frame rate from `params["fps"]` or else the
        video's own.
    """
    detections = parse_detections(detections_path.read_bytes())
    tracks = track_detections_detailed(
        detections,
        max_distance=params["max_distance"],
        max_missed_frames=params["max_missed_frames"],
        max_tracks=params.get("max_tracks"),
        on_progress=on_progress,
    )
    return tracks, params.get("fps") or _video_fps(video_path)


async def run_positional_tracking_job(
    processing_run_id: uuid.UUID,
    detections_file_version_id: uuid.UUID,
    video_file_version_id: uuid.UUID,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID,
    params: dict,
) -> None:
    """Track stored detections and save the trajectories.

    Besides the CSV, one `Track` row is stored per track with its first and
    last frame. On success the run's `runtime_info` holds the track count,
    the frame rate and the number of points.

    The frame rate fills `timestamp_ms` and is recorded as the dataset's
    sampling rate. If the detections were sampled with `frame_step` above 1
    and no `fps` is given, the video's own rate is used, which overstates the
    rate of the sampled frames.

    Args:
        processing_run_id: The run created by the endpoint, in status `queued`.
        detections_file_version_id: The detections JSON file version.
        video_file_version_id: The source video file version.
        experiment_id: The experiment the outputs belong to.
        user_id: The user who started the run.
        params: `max_distance`, `max_missed_frames`, and optionally
            `max_tracks` and `fps`.
    """
    async with AsyncSessionLocal() as db:
        run = await db.get(ProcessingRun, processing_run_id)
        try:
            run.status = "running"
            run.started_at = datetime.now(timezone.utc)
            await db.commit()

            detections_version = await db.get(FileVersion, detections_file_version_id)
            video_version = await db.get(FileVersion, video_file_version_id)
            run_id_str = str(processing_run_id)
            tracks, fps = await asyncio.to_thread(
                _track_from_artifact,
                storage.full_path(detections_version.storage_key),
                str(storage.full_path(video_version.storage_key)),
                params,
                lambda done, total: set_progress(run_id_str, done, total),
            )
            clear_progress(run_id_str)
            tracks = {track_id: points for track_id, points in tracks.items() if points}

            csv_key, checksum, size = storage.save_bytes(
                trajectories_to_csv_bytes(tracks, fps),
                f"experiments/{experiment_id}/processing-runs/{processing_run_id}",
                "positional_tracks.csv",
            )
            out_file = File(
                experiment_id=experiment_id,
                file_type="csv",
                logical_name="positional_tracks.csv",
                is_raw=False,
                created_by=user_id,
            )
            db.add(out_file)
            await db.flush()
            out_version = FileVersion(
                file_id=out_file.id,
                version_number=1,
                storage_bucket=storage.STORAGE_BUCKET,
                storage_key=csv_key,
                mime_type="text/csv",
                size_bytes=size,
                checksum_sha256=checksum,
                uploaded_by=user_id,
                is_current=True,
            )
            db.add(out_version)
            await db.flush()
            out_file.current_version_id = out_version.id

            await get_or_create(db, DatasetType, key=DATASET_TYPE_KEY, defaults={"display_name": "Trajectory Positions"})
            dataset = Dataset(
                experiment_id=experiment_id,
                dataset_type=DATASET_TYPE_KEY,
                name=f"Positional tracks - run {processing_run_id}",
                origin="automatic",
                status="valid",
                created_by=user_id,
            )
            db.add(dataset)
            await db.flush()
            dv = DatasetVersion(
                dataset_id=dataset.id,
                version_number=1,
                schema_version="positional-tracks-1.0",
                changelog="Generated by positional tracking of a stored detection artifact",
                created_by=user_id,
                is_current=True,
            )
            db.add(dv)
            await db.flush()
            dataset.current_version_id = dv.id

            frames = [p.frame for points in tracks.values() for p in points]
            db.add(DatasetFile(dataset_version_id=dv.id, file_version_id=out_version.id, role="primary"))
            db.add(
                DatasetSpatialMetadata(
                    dataset_version_id=dv.id,
                    coordinate_system="pixel",
                    sampling_rate_hz=fps,
                    units="px",
                    frame_start=min(frames, default=None),
                    frame_end=max(frames, default=None),
                )
            )
            db.add(
                ProcessingRunInput(
                    processing_run_id=run.id, artifact_type="file_version",
                    file_version_id=detections_version.id, role="detections",
                )
            )
            db.add(
                ProcessingRunInput(
                    processing_run_id=run.id, artifact_type="file_version",
                    file_version_id=video_version.id, role="raw_video",
                )
            )
            db.add(
                ProcessingRunOutput(
                    processing_run_id=run.id, artifact_type="dataset_version",
                    dataset_version_id=dv.id, role="primary_output",
                )
            )

            for track_id, points in tracks.items():
                db.add(
                    Track(
                        dataset_version_id=dv.id,
                        processing_run_id=run.id,
                        track_label=str(track_id),
                        start_frame=points[0].frame,
                        end_frame=points[-1].frame,
                    )
                )

            run.status = "succeeded"
            run.completed_at = datetime.now(timezone.utc)
            run.runtime_info = {"track_count": len(tracks), "fps": fps, "point_count": len(frames)}
            await db.commit()
        except Exception as exc:
            await db.rollback()
            run = await db.get(ProcessingRun, processing_run_id)
            run.status = "failed"
            run.error_message = str(exc)[:2000]
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
