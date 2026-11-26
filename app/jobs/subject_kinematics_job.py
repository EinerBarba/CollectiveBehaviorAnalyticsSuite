"""Background job for Step 4, Subject Kinematics.

Computes per-frame motion measures for every track in a trajectory CSV, and a
summary per track. See [Subject kinematics](../pipeline/kinematics.md).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from app import storage
from app.crud.base import get_or_create
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
)
from app.tracking.io import kinematics_to_csv_bytes, read_trajectory_csv
from app.tracking.kinematics import compute_kinematics, summarize_track

TOOL_NAME = "Subject Kinematics"
"""Tool name recorded on the run."""

TOOL_VERSION_LABEL = "1.0.0"
"""Tool version recorded on the run."""

DATASET_TYPE_KEY = "subject_kinematics"
"""Dataset type of the output."""


def metric_definitions(fps: float | None) -> dict[str, tuple[str, str]]:
    """Describe the per-track summary metrics.

    Args:
        fps: The frame rate used, which decides whether time units are
            seconds or frames.

    Returns:
        Display name and unit for each metric key produced by
        `summarize_track`.

    Note:
        Metric definitions are registered once, the first time a key is
        used. If the first run had no frame rate, the stored units stay
        `px/frame` even for later runs measured in seconds.
    """
    t = "s" if fps else "frame"
    return {
        "total_distance_px": ("Total Distance Traveled", "px"),
        "net_displacement_px": ("Net Displacement", "px"),
        "path_straightness": ("Path Straightness", "ratio"),
        "mean_speed": ("Mean Speed", f"px/{t}"),
        "max_speed": ("Maximum Speed", f"px/{t}"),
        "mean_acceleration": ("Mean Acceleration", f"px/{t}^2"),
        "max_acceleration": ("Maximum Acceleration", f"px/{t}^2"),
    }


def _compute(trajectory_path, fps: float | None) -> tuple[dict, dict]:
    """Read a trajectory CSV and compute samples and summaries per track. Runs in a worker thread."""
    tracks = read_trajectory_csv(trajectory_path.read_bytes())
    samples = {track_id: compute_kinematics(points, fps) for track_id, points in tracks.items()}
    summaries = {track_id: summarize_track(s) for track_id, s in samples.items()}
    return samples, summaries


async def run_subject_kinematics_job(
    processing_run_id: uuid.UUID,
    trajectory_file_version_id: uuid.UUID,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID,
    fps: float | None,
) -> None:
    """Compute kinematics for a trajectory and store the results.

    Outputs a kinematics CSV in a new `subject_kinematics` dataset, and one
    metric result per track and summary value. Each metric result names its
    track in `value_json["track_label"]`.

    Args:
        processing_run_id: The run, in status `queued`.
        trajectory_file_version_id: The trajectory CSV file version, normally
            the confirmed version from the trajectory editor.
        experiment_id: The experiment the outputs belong to.
        user_id: The user who started the run.
        fps: Frame rate, for units per second. None gives units per frame.
    """
    async with AsyncSessionLocal() as db:
        run = await db.get(ProcessingRun, processing_run_id)
        try:
            run.status = "running"
            run.started_at = datetime.now(timezone.utc)
            await db.commit()

            source_version = await db.get(FileVersion, trajectory_file_version_id)
            samples, summaries = await asyncio.to_thread(_compute, storage.full_path(source_version.storage_key), fps)

            csv_key, checksum, size = storage.save_bytes(
                kinematics_to_csv_bytes(samples, fps),
                f"experiments/{experiment_id}/processing-runs/{processing_run_id}",
                "subject_kinematics.csv",
            )
            out_file = File(
                experiment_id=experiment_id,
                file_type="csv",
                logical_name="subject_kinematics.csv",
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

            await get_or_create(db, DatasetType, key=DATASET_TYPE_KEY, defaults={"display_name": "Subject Kinematics"})
            dataset = Dataset(
                experiment_id=experiment_id,
                dataset_type=DATASET_TYPE_KEY,
                name=f"Subject kinematics - run {processing_run_id}",
                origin="derived",
                status="valid",
                created_by=user_id,
            )
            db.add(dataset)
            await db.flush()
            dv = DatasetVersion(
                dataset_id=dataset.id,
                version_number=1,
                schema_version="subject-kinematics-1.0",
                changelog="Per-frame displacement, speed, acceleration and heading from a trajectory CSV",
                created_by=user_id,
                is_current=True,
            )
            db.add(dv)
            await db.flush()
            dataset.current_version_id = dv.id

            frames = [s.frame for track in samples.values() for s in track]
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
                    file_version_id=source_version.id, role="trajectories",
                )
            )
            db.add(
                ProcessingRunOutput(
                    processing_run_id=run.id, artifact_type="dataset_version",
                    dataset_version_id=dv.id, role="primary_output",
                )
            )

            definitions = metric_definitions(fps)
            for key, (display_name, unit) in definitions.items():
                await get_or_create(
                    db, MetricDefinition, key=key,
                    defaults={"display_name": display_name, "unit": unit, "value_type": "scalar", "scope": "individual"},
                )
            for track_id, summary in summaries.items():
                for key, value in summary.items():
                    db.add(
                        MetricResult(
                            dataset_version_id=dv.id,
                            processing_run_id=run.id,
                            metric_key=key,
                            value_numeric=value,
                            value_json={"track_label": str(track_id)},
                        )
                    )

            run.status = "succeeded"
            run.completed_at = datetime.now(timezone.utc)
            run.runtime_info = {"track_count": len(samples), "fps": fps, "time_unit": "s" if fps else "frame"}
            await db.commit()
        except Exception as exc:
            await db.rollback()
            run = await db.get(ProcessingRun, processing_run_id)
            run.status = "failed"
            run.error_message = str(exc)[:2000]
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
