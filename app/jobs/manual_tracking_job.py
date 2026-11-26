"""Background job for Step 1, Light Tracking.

Builds the light stimulus's trajectory from the researcher's calibration, or
a placeholder trajectory for a video without a stimulus. The run's parameters
also serve as the source of the arena's center and radius for later steps.
See [Light tracking](../pipeline/light-tracking.md).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from app import storage
from app.crud.base import get_or_create
from app.cv.manual_tracking import (
    ManualTrackingConfig,
    generate_manual_trajectory,
    generate_no_stimulus_trajectory,
    trajectory_csv_bytes,
)
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

TOOL_NAME = "Manual Circular Trajectory"
"""Tool name recorded on the run. Later steps find light-tracking runs by this name."""

TOOL_VERSION_LABEL = "1.0.0"
"""Tool version recorded on the run."""

DATASET_TYPE_KEY = "trajectory_positions"
"""Dataset type of the output. The same type is used for subject trajectories."""


async def run_manual_tracking_job(
    processing_run_id: uuid.UUID,
    file_version_id: uuid.UUID,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID,
    config_data: dict,
) -> None:
    """Generate and store the light trajectory for a video.

    A video counts as having a stimulus if `config_data` has a `first_frame`.
    Either way the result is a light-trajectory CSV in a new
    `trajectory_positions` dataset, one `Track` row covering the whole video,
    and metric results for the circle's center and radius and, with a
    stimulus, the rotation period, angular velocity, angular displacement and
    revolution count. The run's `runtime_info` holds the summary values from
    the trajectory generator.

    Args:
        processing_run_id: The run, in status `queued`.
        file_version_id: The video file version.
        experiment_id: The experiment the outputs belong to.
        user_id: The user who started the run.
        config_data: Fields of `ManualTrackingConfig`. Without a stimulus it
            must still hold `center_x`, `center_y` and `radius_px`, which
            describe the arena.
    """
    async with AsyncSessionLocal() as db:
        run = await db.get(ProcessingRun, processing_run_id)
        try:
            run.status = "running"
            run.started_at = datetime.now(timezone.utc)
            await db.commit()

            source_version = await db.get(FileVersion, file_version_id)
            video_path = storage.full_path(source_version.storage_key)

            is_stimulus = config_data.get("first_frame") is not None
            if is_stimulus:
                config = ManualTrackingConfig(**config_data)
                trajectory, metrics = await asyncio.to_thread(generate_manual_trajectory, video_path, config)
            else:
                config = None
                trajectory, metrics = await asyncio.to_thread(generate_no_stimulus_trajectory, video_path)

            csv_key, checksum, size = storage.save_bytes(
                trajectory_csv_bytes(trajectory),
                f"experiments/{experiment_id}/processing-runs/{processing_run_id}",
                "manual_trajectory.csv",
            )
            output_file = File(
                experiment_id=experiment_id,
                file_type="csv",
                logical_name="manual_trajectory.csv",
                is_raw=False,
                created_by=user_id,
            )
            db.add(output_file)
            await db.flush()
            output_version = FileVersion(
                file_id=output_file.id,
                version_number=1,
                storage_bucket=storage.STORAGE_BUCKET,
                storage_key=csv_key,
                mime_type="text/csv",
                size_bytes=size,
                checksum_sha256=checksum,
                uploaded_by=user_id,
                is_current=True,
            )
            db.add(output_version)
            await db.flush()
            output_file.current_version_id = output_version.id

            await get_or_create(
                db,
                DatasetType,
                key=DATASET_TYPE_KEY,
                defaults={"display_name": "Trajectory Positions"},
            )
            dataset = Dataset(
                experiment_id=experiment_id,
                dataset_type=DATASET_TYPE_KEY,
                name=f"Manual trajectory - run {processing_run_id}",
                origin="manual",
                status="valid",
                created_by=user_id,
            )
            db.add(dataset)
            await db.flush()
            dataset_version = DatasetVersion(
                dataset_id=dataset.id,
                version_number=1,
                schema_version="trajectory-positions-1.0",
                changelog="Generated from manual circle calibration and measured rotation period",
                created_by=user_id,
                is_current=True,
            )
            db.add(dataset_version)
            await db.flush()
            dataset.current_version_id = dataset_version.id
            db.add(DatasetFile(dataset_version_id=dataset_version.id, file_version_id=output_version.id, role="primary"))
            db.add(DatasetSpatialMetadata(
                dataset_version_id=dataset_version.id,
                coordinate_system="pixel",
                sampling_rate_hz=metrics["source_fps"],
                units="px",
                frame_start=0,
                frame_end=len(trajectory) - 1,
            ))
            db.add(ProcessingRunInput(
                processing_run_id=run.id,
                artifact_type="file_version",
                file_version_id=file_version_id,
                role="raw_video",
            ))
            db.add(ProcessingRunOutput(
                processing_run_id=run.id,
                artifact_type="dataset_version",
                dataset_version_id=dataset_version.id,
                role="primary_output",
            ))
            db.add(Track(
                dataset_version_id=dataset_version.id,
                processing_run_id=run.id,
                track_label="manual_circular_motion",
                start_frame=0,
                end_frame=len(trajectory) - 1,
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
            arena_center_x = config.center_x if config else config_data["center_x"]
            arena_center_y = config.center_y if config else config_data["center_y"]
            arena_radius_px = config.radius_px if config else config_data["radius_px"]
            values = {
                "trajectory_center_x": arena_center_x,
                "trajectory_center_y": arena_center_y,
                "trajectory_radius_px": arena_radius_px,
                **{key: metrics[key] for key in definitions if key in metrics},
            }
            for key, (display_name, unit) in definitions.items():
                await get_or_create(
                    db,
                    MetricDefinition,
                    key=key,
                    defaults={"display_name": display_name, "unit": unit, "value_type": "scalar", "scope": "individual"},
                )
                if key in values:
                    db.add(MetricResult(
                        dataset_version_id=dataset_version.id,
                        processing_run_id=run.id,
                        metric_key=key,
                        value_numeric=values[key],
                    ))

            run.status = "succeeded"
            run.completed_at = datetime.now(timezone.utc)
            run.runtime_info = metrics
            await db.commit()
        except Exception as exc:
            await db.rollback()
            run = await db.get(ProcessingRun, processing_run_id)
            run.status = "failed"
            run.error_message = str(exc)[:2000]
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()