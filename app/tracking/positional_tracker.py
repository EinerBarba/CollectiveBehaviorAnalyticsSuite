"""Links per-frame subject detections into tracks.

Frames are processed in order. In each frame the tracker pairs existing tracks
with detections using the Hungarian algorithm, so the total distance between
each track and its matched detection is as small as possible. See
[Subject tracking](../pipeline/tracking.md) for the full description.

Frame IDs are taken from the keys of the detection map. A frame ID that is
skipped between two present ones is treated as a frame with no detections.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

Point = tuple[float, float]
"""An (x, y) position in video pixels."""

_OUT_OF_RANGE_COST = 1e9
"""Cost given to track-detection pairs beyond the maximum distance, so they are never preferred."""

DetectionMap = Mapping[int, Sequence[Sequence[float]]]
"""Detections per frame: a mapping from frame ID to a list of [x, y] positions."""


@dataclass(frozen=True)
class TrackPoint:
    """One position of a track in one frame.

    Attributes:
        frame: Frame number.
        x: Horizontal position in pixels.
        y: Vertical position in pixels.
        is_predicted: True if the position is a placeholder held over from the
            last detection because no detection matched in this frame.
    """

    frame: int
    x: float
    y: float
    is_predicted: bool


@dataclass
class TrackState:
    """The running state of one track while the tracker is processing frames.

    Attributes:
        track_id: Identifier of the track, starting at 1.
        current_position: Latest position, either detected or held over.
        previous_position: Position before the latest one, if any.
        velocity: Displacement between the last two detections. It is recorded
            but not used to predict where the subject will go.
        missed_frames: Consecutive frames without a matching detection.
        trajectory: Every position of the track, one per frame, in order.
        predicted_trajectory: Parallel to `trajectory`. Holds the held-over
            position for frames with no detection, and None for detected frames.
        start_frame: Frame in which the track began.
        hits: Number of frames in which a detection matched, counting the first.
        confirmed: Whether the track has reached the required number of hits
            and is reported in the output.
    """

    track_id: int
    current_position: Point
    previous_position: Point | None = None
    velocity: Point = (0.0, 0.0)
    missed_frames: int = 0
    trajectory: list[Point] = field(default_factory=list)
    predicted_trajectory: list[Point | None] = field(default_factory=list)
    start_frame: int = 0
    hits: int = 1
    confirmed: bool = True

    def points(self, strip_trailing_predicted: bool = True) -> list[TrackPoint]:
        """Return the track as a list of points.

        Args:
            strip_trailing_predicted: If True, held-over positions at the very
                end of the track are removed, so the track stops at its last
                real detection.

        Returns:
            One point per frame, in order, with predicted points flagged.
        """
        points = [
            TrackPoint(self.start_frame + offset, point[0], point[1], predicted is not None)
            for offset, (point, predicted) in enumerate(zip(self.trajectory, self.predicted_trajectory))
        ]
        if strip_trailing_predicted:
            while points and points[-1].is_predicted:
                points.pop()
        return points

    def predict(self) -> Point:
        """Return where the track is expected to be in the next frame.

        There is no motion model, so this is simply the current position.
        """
        return self.current_position

    def advance_without_detection(self, prediction: Point) -> None:
        """Move on one frame with no matching detection.

        Records `prediction` as a held-over position, flagged as predicted,
        and counts one more missed frame.

        Args:
            prediction: The position to hold for this frame.
        """
        self.previous_position = self.current_position
        self.current_position = prediction
        self.missed_frames += 1
        self.trajectory.append(prediction)
        self.predicted_trajectory.append(prediction)

    def update(self, detection: Point) -> None:
        """Move on one frame with a matching detection.

        Records the detection, updates the velocity, resets the missed-frame
        count and adds one hit.

        Args:
            detection: The matched position.
        """
        self.previous_position = self.current_position
        self.velocity = (
            detection[0] - self.current_position[0],
            detection[1] - self.current_position[1],
        )
        self.current_position = detection
        self.missed_frames = 0
        self.hits += 1
        self.trajectory.append(detection)
        self.predicted_trajectory.append(None)


class PositionalTracker:
    """Tracks subjects by matching detections frame by frame.

    Call `update` once per frame, in order. Tracks that stay unmatched for too
    long are moved to a finished list. When all frames have been processed,
    read the result with `track_points` or `trajectories`.

    Args:
        max_distance: Farthest, in pixels, a track may move between frames and
            still be matched to a detection. Must be positive.
        max_missed_frames: Consecutive frames a track may go unmatched before
            it ends. Zero ends a track at its first missed frame.
        start_frame: Frame number of the first call to `update`.
        max_tracks: Upper bound on the number of tracks ever confirmed, normally
            the number of subjects. None means no limit.
        min_hits: Matched detections a new track needs before it is accepted.
            A tentative track that goes unmatched before then is dropped.
            Must be at least 1.

    Raises:
        ValueError: If `min_hits`, `max_distance`, `max_missed_frames` or
            `max_tracks` is outside its allowed range.
    """

    def __init__(
        self,
        max_distance: float = 50.0,
        max_missed_frames: int = 5,
        start_frame: int = 0,
        max_tracks: int | None = None,
        min_hits: int = 1,
    ) -> None:
        if min_hits < 1:
            raise ValueError("min_hits must be at least 1")
        if max_distance <= 0:
            raise ValueError("max_distance must be positive")
        if max_missed_frames < 0:
            raise ValueError("max_missed_frames must be non-negative")
        if max_tracks is not None and max_tracks <= 0:
            raise ValueError("max_tracks must be positive")
        self.max_distance = float(max_distance)
        self.max_missed_frames = int(max_missed_frames)
        self.max_tracks = max_tracks
        self.min_hits = int(min_hits)
        self._confirmed_count = 0
        self._next_id = 1
        self._frame = int(start_frame)
        self._tracks: dict[int, TrackState] = {}
        self._finished: dict[int, TrackState] = {}

    @property
    def active_tracks(self) -> dict[int, TrackState]:
        """Tracks still open, keyed by track ID. This is a copy of the dictionary."""
        return dict(self._tracks)

    def update(self, detections: Sequence[Sequence[float]]) -> dict[int, TrackState]:
        """Process one frame.

        Matches the detections to open tracks, extends the matched tracks,
        holds unmatched tracks in place, closes tracks that missed too many
        frames, and starts new tracks from leftover detections.

        Args:
            detections: The [x, y] positions found in this frame. May be empty.

        Returns:
            The tracks still open after this frame, keyed by track ID.

        Raises:
            ValueError: If a detection does not have exactly two coordinates.
        """
        points = [_point(detection) for detection in detections]
        track_items = list(self._tracks.items())
        predictions = [track.predict() for _, track in track_items]
        assignments, unmatched_tracks, unmatched_detections = self._assign(predictions, points)

        for track_index, detection_index in assignments:
            track_id, track = track_items[track_index]
            track.update(points[detection_index])
            if not track.confirmed and track.hits >= self.min_hits:
                if self.max_tracks is None or self._confirmed_count < self.max_tracks:
                    track.confirmed = True
                    self._confirmed_count += 1
                else:
                    del self._tracks[track_id]

        expired: list[int] = []
        for track_index in unmatched_tracks:
            track_id, track = track_items[track_index]
            if not track.confirmed:
                del self._tracks[track_id]
                continue
            track.advance_without_detection(predictions[track_index])
            if track.missed_frames > self.max_missed_frames:
                expired.append(track_id)
        for track_id in expired:
            self._finished[track_id] = self._tracks[track_id]
            del self._tracks[track_id]

        new_detection_indices = sorted(unmatched_detections)
        if self.max_tracks is not None:
            available_slots = max(0, self.max_tracks - self._confirmed_count)
            if self.min_hits <= 1:
                new_detection_indices = new_detection_indices[:available_slots]
            elif available_slots == 0:
                new_detection_indices = []

        for detection_index in new_detection_indices:
            point = points[detection_index]
            track = TrackState(
                track_id=self._next_id,
                current_position=point,
                trajectory=[point],
                predicted_trajectory=[None],
                start_frame=self._frame,
                confirmed=self.min_hits <= 1,
            )
            if track.confirmed:
                self._confirmed_count += 1
            self._tracks[self._next_id] = track
            self._next_id += 1

        self._frame += 1
        return self.active_tracks

    def _assign(
        self,
        predictions: Sequence[Point],
        detections: Sequence[Point],
    ) -> tuple[list[tuple[int, int]], set[int], set[int]]:
        track_count = len(predictions)
        detection_count = len(detections)
        if not track_count:
            return [], set(), set(range(detection_count))
        if not detection_count:
            return [], set(range(track_count)), set()

        cost = np.array(
            [[np.linalg.norm(np.subtract(prediction, detection)) for detection in detections]
             for prediction in predictions],
            dtype=float,
        )
        # Pairs beyond max_distance are made prohibitively expensive before solving, so an
        # out-of-range pair can never take a detection away from a valid in-range match.
        gated = np.where(cost <= self.max_distance, cost, _OUT_OF_RANGE_COST)
        row_indices, column_indices = linear_sum_assignment(gated)
        assignments = [
            (int(row), int(column))
            for row, column in zip(row_indices, column_indices)
            if cost[row, column] <= self.max_distance
        ]
        assigned_tracks = {row for row, _ in assignments}
        assigned_detections = {column for _, column in assignments}
        return (
            assignments,
            set(range(track_count)) - assigned_tracks,
            set(range(detection_count)) - assigned_detections,
        )

    def track_points(self) -> dict[int, list[TrackPoint]]:
        """Return every confirmed track as a list of points.

        Tracks that ended after missing frames keep their held-over positions.
        Tracks still open at the end of the video drop trailing held-over
        positions, so they stop at their last real detection.

        Returns:
            Points per track, keyed by track ID, with predicted points flagged.
        """
        # Finished (expired) tracks: keep predicted gap frames so they appear in the output.
        # Active tracks at end-of-video: strip trailing predicted to avoid ghost future positions.
        result = {track_id: track.points(strip_trailing_predicted=False) for track_id, track in self._finished.items()}
        result.update({
            track_id: track.points(strip_trailing_predicted=True)
            for track_id, track in self._tracks.items() if track.confirmed
        })
        return result

    def trajectories(self, include_predicted: bool = True) -> dict[int, list[Point]]:
        """Return every confirmed track as a plain list of positions.

        Args:
            include_predicted: If False, held-over positions are left out and
                only real detections remain.

        Returns:
            Positions per track, keyed by track ID, without frame numbers.
        """
        all_tracks = {**self._finished, **{i: t for i, t in self._tracks.items() if t.confirmed}}
        if include_predicted:
            return {track_id: list(track.trajectory) for track_id, track in all_tracks.items()}
        return {
            track_id: [point for point, predicted in zip(track.trajectory, track.predicted_trajectory) if predicted is None]
            for track_id, track in all_tracks.items()
        }


def _run_tracker(
    all_points: DetectionMap | Iterable[tuple[int, Sequence[Sequence[float]]]],
    max_distance: float,
    max_missed_frames: int,
    max_tracks: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    min_hits: int = 1,
) -> PositionalTracker:
    frame_items = all_points.items() if isinstance(all_points, Mapping) else all_points
    ordered = sorted((int(frame_id), detections) for frame_id, detections in frame_items)
    tracker = PositionalTracker(
        max_distance=max_distance,
        max_missed_frames=max_missed_frames,
        start_frame=ordered[0][0] if ordered else 0,
        max_tracks=max_tracks,
        min_hits=min_hits,
    )
    total = len(ordered)
    previous_frame = ordered[0][0] if ordered else 0
    for idx, (frame_id, detections) in enumerate(ordered):
        for _ in range(max(0, frame_id - previous_frame - 1)):
            tracker.update([])
        tracker.update(detections)
        previous_frame = frame_id
        if on_progress and (idx % 50 == 0 or idx == total - 1):
            on_progress(idx + 1, total)
    return tracker


def track_unclaimed_detections(
    all_points: DetectionMap,
    claimed: Mapping[int, Sequence[Sequence[float]]],
    num_tracks: int,
    max_distance: float,
    max_missed_frames: int,
    claim_radius: float = 6.0,
    min_hits: int = 5,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[int, list[TrackPoint]]:
    """Find new tracks among detections that no existing track uses.

    This powers the editor's iterative step. Detections within `claim_radius`
    of a point in `claimed`, in the same frame, are removed first. The tracker
    then runs on what is left and returns tracks that contain at least one real
    detection.

    Args:
        all_points: Detections per frame for the whole video.
        claimed: Positions already used by existing tracks, per frame.
        num_tracks: Most new tracks to return.
        max_distance: Farthest, in pixels, a track may move between frames.
        max_missed_frames: Consecutive missed frames before a track ends.
        claim_radius: Distance, in pixels, within which a detection counts as
            already used.
        min_hits: Matched detections a new track needs before it is accepted.
        on_progress: Optional callback, called with (frames done, total frames).

    Returns:
        New tracks as lists of points, ordered by start frame and keyed by
        track ID.
    """
    limit_sq = claim_radius * claim_radius
    remaining: dict[int, list[Sequence[float]]] = {}
    for frame, detections in all_points.items():
        covered = claimed.get(int(frame), ())
        remaining[int(frame)] = [
            d for d in detections
            if not any((d[0] - c[0]) ** 2 + (d[1] - c[1]) ** 2 <= limit_sq for c in covered)
        ]
    tracker = _run_tracker(remaining, max_distance, max_missed_frames, num_tracks, on_progress, min_hits)
    tracks = {tid: pts for tid, pts in tracker.track_points().items() if any(not p.is_predicted for p in pts)}
    return dict(sorted(tracks.items(), key=lambda item: item[1][0].frame))


def track_detections(
    all_points: DetectionMap | Iterable[tuple[int, Sequence[Sequence[float]]]],
    max_distance: float = 50.0,
    max_missed_frames: int = 5,
    max_tracks: int | None = None,
) -> dict[int, list[Point]]:
    """Track a whole video and return plain position lists.

    Args:
        all_points: Detections per frame.
        max_distance: Farthest, in pixels, a track may move between frames.
        max_missed_frames: Consecutive missed frames before a track ends.
        max_tracks: Upper bound on the number of tracks, or None for no limit.

    Returns:
        Positions per track, keyed by track ID, including held-over positions.
    """
    return _run_tracker(all_points, max_distance, max_missed_frames, max_tracks).trajectories()


def track_detections_detailed(
    all_points: DetectionMap | Iterable[tuple[int, Sequence[Sequence[float]]]],
    max_distance: float = 50.0,
    max_missed_frames: int = 5,
    max_tracks: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[int, list[TrackPoint]]:
    """Track a whole video and return points with frame numbers.

    This is the function the tracking job calls.

    Args:
        all_points: Detections per frame.
        max_distance: Farthest, in pixels, a track may move between frames.
        max_missed_frames: Consecutive missed frames before a track ends.
        max_tracks: Upper bound on the number of tracks, or None for no limit.
        on_progress: Optional callback, called with (frames done, total frames).

    Returns:
        Points per track, keyed by track ID, with predicted points flagged.
    """
    return _run_tracker(all_points, max_distance, max_missed_frames, max_tracks, on_progress).track_points()


def _point(value: Sequence[float]) -> Point:
    if len(value) != 2:
        raise ValueError(f"A detection must contain exactly two coordinates: {value}")
    return float(value[0]), float(value[1])