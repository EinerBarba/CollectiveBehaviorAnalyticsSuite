"""Per-subject motion measures computed from a trajectory.

Only detected points are used. Predicted placeholders are skipped, so a gap
in a track is bridged by one longer step between the detections either side
of it. See [Subject kinematics](../pipeline/kinematics.md).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from app.tracking.positional_tracker import TrackPoint


@dataclass(frozen=True)
class KinematicSample:
    """Motion of one subject at one detected point.

    All motion fields describe the step from the previous detected point to
    this one. They are None on a track's first point, and `acceleration` is
    also None on its second.

    Attributes:
        frame: Frame number.
        x: Horizontal position in pixels.
        y: Vertical position in pixels.
        dx: Change in x since the previous point, in pixels.
        dy: Change in y since the previous point, in pixels.
        displacement: Straight-line distance since the previous point, in pixels.
        speed: `displacement` divided by the time between the two points, in
            pixels per second, or pixels per frame without a frame rate.
        acceleration: Size of the change in velocity between the last two
            steps, divided by the mean of their durations. It is a magnitude,
            so turning at constant speed also counts as acceleration.
        heading_deg: Direction of the step in degrees, from -180 to 180, with
            0 pointing right and 90 pointing down the image. None if the
            subject did not move.
    """

    frame: int
    x: float
    y: float
    dx: float | None = None
    dy: float | None = None
    displacement: float | None = None 
    speed: float | None = None
    acceleration: float | None = None 
    heading_deg: float | None = None


def compute_kinematics(points: Sequence[TrackPoint], fps: float | None = None) -> list[KinematicSample]:
    """Compute motion measures along one track.

    Args:
        points: The track's points, in any order. Predicted points are ignored.
        fps: Frame rate, to express time in seconds. Without it, time is
            measured in frames.

    Returns:
        One sample per detected point, in frame order.
    """
    observed = sorted((p for p in points if not p.is_predicted), key=lambda p: p.frame)
    frame_seconds = 1.0 / fps if fps else 1.0
    samples: list[KinematicSample] = []
    previous_velocity: tuple[float, float] | None = None
    previous_dt: float | None = None
    for i, p in enumerate(observed):
        if i == 0:
            samples.append(KinematicSample(p.frame, p.x, p.y))
            continue
        q = observed[i - 1]
        dx, dy = p.x - q.x, p.y - q.y
        dt = (p.frame - q.frame) * frame_seconds
        velocity = (dx / dt, dy / dt)
        displacement = math.hypot(dx, dy)
        acceleration = None
        if previous_velocity is not None:
            step = (dt + previous_dt) / 2
            acceleration = math.hypot(velocity[0] - previous_velocity[0], velocity[1] - previous_velocity[1]) / step
        samples.append(
            KinematicSample(
                frame=p.frame,
                x=p.x,
                y=p.y,
                dx=dx,
                dy=dy,
                displacement=displacement,
                speed=displacement / dt,
                acceleration=acceleration,
                heading_deg=math.degrees(math.atan2(dy, dx)) if displacement > 0 else None,
            )
        )
        previous_velocity, previous_dt = velocity, dt
    return samples


def summarize_track(samples: Sequence[KinematicSample]) -> dict[str, float]:
    """Summarize a track's motion in a few numbers.

    Args:
        samples: The track's samples, as returned by `compute_kinematics`.

    Returns:
        A dictionary with `total_distance_px` (sum of all steps) and
        `net_displacement_px` (first to last point). It also has
        `path_straightness` (net divided by total, from 0 to 1) if the subject
        moved, `mean_speed` and `max_speed` if any speed exists, and
        `mean_acceleration` and `max_acceleration` if any acceleration exists.
        Empty if there are no samples.
    """
    if not samples:
        return {}
    speeds = [s.speed for s in samples if s.speed is not None]
    accelerations = [s.acceleration for s in samples if s.acceleration is not None]
    total = sum(s.displacement for s in samples if s.displacement is not None)
    net = math.hypot(samples[-1].x - samples[0].x, samples[-1].y - samples[0].y)
    summary = {"total_distance_px": total, "net_displacement_px": net}
    if total > 0:
        summary["path_straightness"] = net / total
    if speeds:
        summary["mean_speed"] = sum(speeds) / len(speeds)
        summary["max_speed"] = max(speeds)
    if accelerations:
        summary["mean_acceleration"] = sum(accelerations) / len(accelerations)
        summary["max_acceleration"] = max(accelerations)
    return summary
