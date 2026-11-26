"""Reading and writing the file formats used between pipeline steps.

- **Detections** are JSON: an object mapping each frame ID (as a string) to a
  list of `[x, y]` positions.
- **Trajectories** are CSV with the columns in `TRAJECTORY_CSV_FIELDS`, one
  row per track point.
- **Kinematics** are CSV with the columns in `KINEMATICS_CSV_FIELDS`.
"""

from __future__ import annotations

import csv
import io
import json
import math
from typing import Mapping, Sequence

from app.tracking.kinematics import KinematicSample
from app.tracking.positional_tracker import Point, TrackPoint

TRAJECTORY_CSV_FIELDS = ["track_id", "frame", "timestamp_ms", "x", "y", "is_predicted"]
"""Columns of a trajectory CSV. `is_predicted` is the text `true` or `false`."""

KINEMATICS_CSV_FIELDS = [
    "track_id", "frame", "timestamp_ms", "x", "y", "dx", "dy",
    "displacement_px", "speed", "acceleration", "heading_deg",
]
"""Columns of a kinematics CSV. Motion columns are empty where a value is undefined."""


def _timestamp_ms(frame: int, fps: float | None) -> int | str:
    return int(frame * 1000 / fps) if fps else ""


def parse_detections(raw: bytes | str | Mapping) -> dict[int, list[Point]]:
    """Read and validate a detections file.

    Args:
        raw: The JSON as bytes or text, or an already-parsed mapping.

    Returns:
        Detections per frame, keyed by integer frame ID.

    Raises:
        ValueError: If the data is not an object, a frame ID is not a
            non-negative integer or appears twice, or a detection is not a
            pair of finite numbers.
    """
    data = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
    if not isinstance(data, Mapping):
        raise ValueError("Detections must be a JSON object mapping frame IDs to lists of [x, y]")
    frames: dict[int, list[Point]] = {}
    for key, points in data.items():
        try:
            frame_id = int(key)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid frame ID: {key!r}") from None
        if frame_id < 0 or frame_id in frames:
            raise ValueError(f"Invalid or duplicate frame ID: {key!r}")
        if not isinstance(points, Sequence) or isinstance(points, (str, bytes)):
            raise ValueError(f"Frame {key}: detections must be a list of [x, y]")
        frames[frame_id] = [_parse_point(frame_id, point) for point in points]
    return frames


def _parse_point(frame_id: int, point: object) -> Point:
    if not isinstance(point, Sequence) or isinstance(point, (str, bytes)) or len(point) != 2:
        raise ValueError(f"Frame {frame_id}: a detection must be [x, y], got {point!r}")
    try:
        x, y = float(point[0]), float(point[1])
    except (TypeError, ValueError):
        raise ValueError(f"Frame {frame_id}: non-numeric detection {point!r}") from None
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError(f"Frame {frame_id}: non-finite detection {point!r}")
    return x, y


def trajectories_to_csv_bytes(tracks: Mapping[int, Sequence[TrackPoint]], fps: float | None = None) -> bytes:
    """Write tracks as a trajectory CSV.

    Args:
        tracks: Points per track, keyed by track ID.
        fps: Frame rate, to fill `timestamp_ms`. Left empty without it.

    Returns:
        UTF-8 CSV, with tracks in ID order.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(TRAJECTORY_CSV_FIELDS)
    for track_id in sorted(tracks):
        for p in tracks[track_id]:
            writer.writerow([track_id, p.frame, _timestamp_ms(p.frame, fps), p.x, p.y, str(p.is_predicted).lower()])
    return buf.getvalue().encode("utf-8")


def read_trajectory_csv(raw: bytes | str) -> dict[int, list[TrackPoint]]:
    """Read a trajectory CSV.

    Extra columns are ignored and a UTF-8 byte-order mark is accepted.

    Args:
        raw: The CSV as bytes or text.

    Returns:
        Points per track, keyed by track ID, each sorted by frame.

    Raises:
        ValueError: If a required column is missing or a row cannot be parsed.
    """
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
    reader = csv.DictReader(io.StringIO(text))
    missing = {"track_id", "frame", "x", "y", "is_predicted"} - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"Trajectory CSV is missing columns: {sorted(missing)}")
    tracks: dict[int, list[TrackPoint]] = {}
    for line_number, row in enumerate(reader, start=2):
        try:
            point = TrackPoint(int(row["frame"]), float(row["x"]), float(row["y"]), row["is_predicted"].strip().lower() == "true")
            tracks.setdefault(int(row["track_id"]), []).append(point)
        except (TypeError, ValueError):
            raise ValueError(f"Trajectory CSV line {line_number}: invalid row {row!r}") from None
    return {track_id: sorted(points, key=lambda p: p.frame) for track_id, points in tracks.items()}


def kinematics_to_csv_bytes(samples: Mapping[int, Sequence[KinematicSample]], fps: float | None = None) -> bytes:
    """Write kinematic samples as a kinematics CSV.

    Args:
        samples: Samples per track, keyed by track ID.
        fps: Frame rate, to fill `timestamp_ms`. Left empty without it.

    Returns:
        UTF-8 CSV, with tracks in ID order.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(KINEMATICS_CSV_FIELDS)
    for track_id in sorted(samples):
        for s in samples[track_id]:
            row = [s.dx, s.dy, s.displacement, s.speed, s.acceleration, s.heading_deg]
            writer.writerow(
                [track_id, s.frame, _timestamp_ms(s.frame, fps), s.x, s.y] + ["" if v is None else v for v in row]
            )
    return buf.getvalue().encode("utf-8")


def detections_to_json_bytes(points: Mapping[int, Sequence[Point]]) -> bytes:
    """Write detections as a detections JSON file, with frames in order.

    Args:
        points: Detections per frame, keyed by frame ID.

    Returns:
        UTF-8 JSON.
    """
    return json.dumps({str(frame): [[x, y] for x, y in pts] for frame, pts in sorted(points.items())}).encode("utf-8")
