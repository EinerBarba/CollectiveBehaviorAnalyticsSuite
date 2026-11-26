"""Background job for Step 2, Subject Detection.

Runs `detect_subjects` on a video and stores the result as a detections JSON
file in a new `subject_detections` dataset. See
[Background jobs](../jobs.md) for the steps every job follows.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from app import storage
from app.crud.base import get_or_create
from app.cv.subject_detection import detect_subjects
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
)
from app.tracking.io import detections_to_json_bytes

TOOL_NAME = "Subject Detector"
"""Tool name recorded on the run. Other code finds detection runs by this name."""

TOOL_VERSION_LABEL = "1.0.0"
"""Tool version recorded on the run."""

DATASET_TYPE_KEY = "subject_detections"
"""Dataset type of the output."""


async def run_subject_detection_job(
    processing_run_id: uuid.UUID,
    file_version_id: uuid.UUID,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID,
    params: dict,
) -> None:
    """Detect subjects in a video and store the detections.

    On success the run's `runtime_info` holds the frame count, the effective
    frame rate, the arena found, the minimum, maximum and mean detections per
    frame, and the ID of the detections file version. Frame keys in the file
    are sample indices, so with `frame_step` above 1 they do not match the
    video's own frame numbers.

    Args:
        processing_run_id: The run created by the endpoint, in status `queued`.
        file_version_id: The video file version.
        experiment_id: The experiment the outputs belong to.
        user_id: The user who started the run.
        params: Keyword arguments passed to `detect_subjects`, such as the
            area, brightness and shape limits, `frame_step` and an optional
            manual arena.
    """
    async with AsyncSessionLocal() as db:
        run = await db.get(ProcessingRun, processing_run_id)
        try:
            run.status = "running"
            run.started_at = datetime.now(timezone.utc)
            await db.commit()

            video_version = await db.get(FileVersion, file_version_id)
            run_id_str = str(processing_run_id)
            result = await asyncio.to_thread(
                detect_subjects,
                str(storage.full_path(video_version.storage_key)),
                **params,
                on_progress=lambda done, total: set_progress(run_id_str, done, total),
            )
            clear_progress(run_id_str)
            points, fps = result["points"], result["fps"]

            json_key, checksum, size = storage.save_bytes(
                detections_to_json_bytes(points),
                f"experiments/{experiment_id}/processing-runs/{processing_run_id}",
                "detections.json",
            )
            out_file = File(
                experiment_id=experiment_id,
                file_type="json",
                logical_name="detections.json",
                is_raw=False,
                created_by=user_id,
            )
            db.add(out_file)
            await db.flush()
            out_version = FileVersion(
                file_id=out_file.id,
                version_number=1,
                storage_bucket=storage.STORAGE_BUCKET,
                storage_key=json_key,
                mime_type="application/json",
                size_bytes=size,
                checksum_sha256=checksum,
                uploaded_by=user_id,
                is_current=True,
            )
            db.add(out_version)
            await db.flush()
            out_file.current_version_id = out_version.id

            await get_or_create(db, DatasetType, key=DATASET_TYPE_KEY, defaults={"display_name": "Subject Detections"})
            dataset = Dataset(
                experiment_id=experiment_id,
                dataset_type=DATASET_TYPE_KEY,
                name=f"Subject detections - run {processing_run_id}",
                origin="automatic",
                status="valid",
                created_by=user_id,
            )
            db.add(dataset)
            await db.flush()
            dv = DatasetVersion(
                dataset_id=dataset.id,
                version_number=1,
                schema_version="subject-detections-1.0",
                changelog="Per-frame bright-spot detections inside the detected arena",
                created_by=user_id,
                is_current=True,
            )
            db.add(dv)
            await db.flush()
            dataset.current_version_id = dv.id

            db.add(DatasetFile(dataset_version_id=dv.id, file_version_id=out_version.id, role="primary"))
            db.add(
                DatasetSpatialMetadata(
                    dataset_version_id=dv.id,
                    coordinate_system="pixel",
                    sampling_rate_hz=fps,
                    units="px",
                    frame_start=min(points),
                    frame_end=max(points),
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

            counts = [len(p) for p in points.values()]
            h, k, r = result["plate"]
            run.status = "succeeded"
            run.completed_at = datetime.now(timezone.utc)
            run.runtime_info = {
                "frame_count": result["frame_count"],
                "fps": fps,
                "plate": {"center_x": h, "center_y": k, "radius_px": r},
                "detections_per_frame": {"min": min(counts), "max": max(counts), "mean": sum(counts) / len(counts)},
                "detections_file_version_id": str(out_version.id),
            }
            await db.commit()
        except Exception as exc:
            await db.rollback()
            run = await db.get(ProcessingRun, processing_run_id)
            run.status = "failed"
            run.error_message = str(exc)[:2000]
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
