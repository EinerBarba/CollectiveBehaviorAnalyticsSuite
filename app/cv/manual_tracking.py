"""Light-stimulus trajectories from a manual calibration.

The light is assumed to move around a circle at a constant speed. The
researcher marks the circle, one position of the light, and how many frames a
full rotation takes. From that, the light's position is computed for every
frame of the video. See [Light tracking](../pipeline/light-tracking.md).
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import cv2


@dataclass(frozen=True)
class ManualTrackingConfig:
    """The researcher's calibration of the light's circular path.

    Attributes:
        center_x: Circle center x, in pixels. Also used as the arena center.
        center_y: Circle center y, in pixels.
        radius_px: Circle radius, in pixels. Also used as the arena radius.
        first_frame: Frame at which the light's position was marked.
        first_x: The light's x position at `first_frame`.
        first_y: The light's y position at `first_frame`.
        frames_per_rotation: Frames the light takes to go once around.
        direction: 1 for increasing angle, -1 for decreasing. In image
            coordinates, where y points down, 1 appears clockwise on screen.
    """

    center_x: float
    center_y: float
    radius_px: float
    first_frame: int
    first_x: float
    first_y: float
    frames_per_rotation: float
    direction: int = 1

    def validate(self, source_frame_count: int | None = None) -> None:
        """Check that the calibration makes sense.

        Args:
            source_frame_count: The video's frame count, to check that
                `first_frame` lies inside it. Skipped if None.

        Raises:
            ValueError: If the radius or rotation length is not positive,
                `first_frame` is negative or beyond the video, or `direction`
                is not 1 or -1.
        """
        if self.radius_px <= 0:
            raise ValueError("radius_px must be positive")
        if self.first_frame < 0:
            raise ValueError("first_frame must be non-negative")
        if self.frames_per_rotation <= 0:
            raise ValueError("frames_per_rotation must be positive")
        if self.direction not in (-1, 1):
            raise ValueError("direction must be 1 or -1")
        if source_frame_count is not None and self.first_frame >= source_frame_count:
            raise ValueError(f"first_frame {self.first_frame} is beyond the video's {source_frame_count} frames")


def video_timeline(video_path: Path) -> tuple[float, int, float]:
    """Read a video's frame rate, frame count and duration.

    Args:
        video_path: The video file.

    Returns:
        Frame rate, frame count, and duration in seconds.

    Raises:
        ValueError: If the video cannot be opened or reports no frames or
            frame rate.
    """
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {video_path.name}")
    try:
        native_fps = float(capture.get(cv2.CAP_PROP_FPS))
        source_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:
        capture.release()
    if native_fps <= 0 or source_frames <= 0:
        raise ValueError("Video FPS or frame count is invalid")
    return native_fps, source_frames, source_frames / native_fps


def generate_manual_trajectory(video_path: Path, config: ManualTrackingConfig) -> tuple[list[dict], dict]:
    """Compute the light's position in every frame from a calibration.

    The angle at `first_frame` comes from the marked position. Each frame
    adds a constant step of 2π / `frames_per_rotation`, signed by
    `direction`. Frames before `first_frame` are extrapolated backwards.

    There is one row per frame of the source video, so the `frame` column
    matches the video's own frame numbers. The output is deliberately not
    resampled to another frame rate, which would break that match.

    Args:
        video_path: The video file.
        config: The calibration.

    Returns:
        The trajectory and a dictionary of summary values.

        Each trajectory row has `frame`, `timestamp_ms`, `x`, `y`,
        `theta_rad`, `unwrapped_angle_rad` and `instantaneous_omega_rad_s`.
        Here `theta_rad` and `unwrapped_angle_rad` hold the same unwrapped
        angle, which keeps growing past 2π.

        The summary has `source_fps`, `source_frame_count`,
        `duration_seconds`, `rotation_period_s`, `angular_velocity_rad_s`,
        `angular_velocity_deg_s`, `angular_displacement_rad` (from
        `first_frame` to the last frame) and `revolution_count`.

    Raises:
        ValueError: If the video cannot be read or the calibration is invalid.
    """
    native_fps, source_frames, duration_seconds = video_timeline(video_path)
    config.validate(source_frames)
    phase = math.atan2(config.first_y - config.center_y, config.first_x - config.center_x)
    angular_velocity = config.direction * 2.0 * math.pi / config.frames_per_rotation
    trajectory: list[dict] = []

    for frame in range(source_frames):
        elapsed = frame - config.first_frame
        angle = phase + angular_velocity * elapsed
        trajectory.append({
            "frame": frame,
            "timestamp_ms": round(frame / native_fps * 1000, 3),
            "x": config.center_x + config.radius_px * math.cos(angle),
            "y": config.center_y + config.radius_px * math.sin(angle),
            "theta_rad": angle,
            "unwrapped_angle_rad": angle,
            "instantaneous_omega_rad_s": angular_velocity * native_fps,
        })

    angular_displacement_rad = angular_velocity * (source_frames - 1 - config.first_frame)
    return trajectory, {
        "source_fps": native_fps,
        "source_frame_count": source_frames,
        "duration_seconds": duration_seconds,
        "rotation_period_s": abs(config.frames_per_rotation / native_fps),
        "angular_velocity_rad_s": angular_velocity * native_fps,
        "angular_velocity_deg_s": math.degrees(angular_velocity * native_fps),
        "angular_displacement_rad": angular_displacement_rad,
        "revolution_count": abs(angular_displacement_rad) / (2.0 * math.pi),
    }


def generate_no_stimulus_trajectory(video_path: Path) -> tuple[list[dict], dict]:
    """Build a placeholder light trajectory for a video with no stimulus.

    Every frame gets position (-1, -1), which the rest of the system reads as
    "light not present", and zero angles.

    Args:
        video_path: The video file.

    Returns:
        The trajectory, in the same row format as
        `generate_manual_trajectory`, and a summary with `source_fps`,
        `source_frame_count` and `duration_seconds`.

    Raises:
        ValueError: If the video cannot be read.
    """
    native_fps, source_frames, duration_seconds = video_timeline(video_path)
    trajectory = [
        {
            "frame": f,
            "timestamp_ms": round(f / native_fps * 1000, 3),
            "x": -1.0,
            "y": -1.0,
            "theta_rad": 0.0,
            "unwrapped_angle_rad": 0.0,
            "instantaneous_omega_rad_s": 0.0,
        }
        for f in range(source_frames)
    ]
    metrics = {
        "source_fps": native_fps,
        "source_frame_count": source_frames,
        "duration_seconds": duration_seconds,
    }
    return trajectory, metrics


def trajectory_csv_bytes(trajectory: list[dict]) -> bytes:
    """Write a light trajectory as CSV.

    Args:
        trajectory: Rows as produced by `generate_manual_trajectory`.

    Returns:
        UTF-8 CSV with a header row and the columns `frame`, `timestamp_ms`,
        `x`, `y`, `theta_rad`, `unwrapped_angle_rad` and
        `instantaneous_omega_rad_s`.
    """
    fields = [
        "frame",
        "timestamp_ms",
        "x",
        "y",
        "theta_rad",
        "unwrapped_angle_rad",
        "instantaneous_omega_rad_s",
    ]
    rows = []
    for point in trajectory:
        rows.append({field: point[field] for field in fields})
    output = __import__("io").StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")