"""Reading video metadata and frames.

Used by the video endpoints to report a video's properties, serve single
frames to the interface, and export frames as JPEG images.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import cv2


VIDEO_EXTENSIONS = {".avi", ".mp4", ".mov", ".mkv", ".wmv", ".m4v"}
"""File extensions accepted for upload and frame extraction."""


@dataclass(frozen=True)
class VideoMetadata:
    """Basic properties of a video, as reported by OpenCV.

    Attributes:
        width: Frame width in pixels.
        height: Frame height in pixels.
        fps: Frames per second.
        frame_count: Number of frames.
        duration_seconds: `frame_count` divided by `fps`.
    """

    width: int
    height: int
    fps: float
    frame_count: int
    duration_seconds: float


@dataclass(frozen=True)
class FrameExtractionResult:
    """What `extract_frames` produced.

    Attributes:
        metadata: The source video's properties.
        requested_fps: The frame rate asked for.
        effective_fps: The frame rate used, never above the video's own.
        frame_count: Number of frames written.
        manifest_path: Path of `manifest.json`.
        output_size_bytes: Total size of everything written.
        checksum_sha256: One SHA-256 checksum over all written files and
            their relative paths.
    """

    metadata: VideoMetadata
    requested_fps: float
    effective_fps: float
    frame_count: int
    manifest_path: Path
    output_size_bytes: int
    checksum_sha256: str


def inspect_video(source_path: Path) -> VideoMetadata:
    """Read a video's dimensions, frame rate and length.

    Args:
        source_path: The video file.

    Returns:
        The video's metadata.

    Raises:
        ValueError: If the video cannot be opened or any value is missing.
    """
    capture = cv2.VideoCapture(str(source_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {source_path.name}")
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        capture.release()

    if fps <= 0 or frame_count <= 0 or width <= 0 or height <= 0:
        raise ValueError("Video metadata is incomplete or invalid")
    return VideoMetadata(width, height, fps, frame_count, frame_count / fps)


def read_frame_jpeg(source_path: Path, frame_index: int, quality: int = 90) -> bytes:
    """Read one frame and encode it as JPEG.

    Args:
        source_path: The video file.
        frame_index: The frame to read, starting at 0.
        quality: JPEG quality from 0 to 100.

    Returns:
        The JPEG bytes.

    Raises:
        ValueError: If the video cannot be opened, the index is out of range,
            or the frame cannot be read or encoded.
    """
    capture = cv2.VideoCapture(str(source_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {source_path.name}")
    try:
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if frame_index < 0 or (frame_count > 0 and frame_index >= frame_count):
            raise ValueError(f"frame_index {frame_index} is out of range (0..{max(frame_count - 1, 0)})")
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
        if not ok or frame is None:
            raise ValueError(f"Could not read frame {frame_index}")
    finally:
        capture.release()

    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("Could not encode frame as JPEG")
    return encoded.tobytes()


def extract_frames(
    source_path: Path,
    output_dir: Path,
    requested_fps: float,
    output_width: int | None = None,
    output_height: int | None = None,
) -> FrameExtractionResult:
    """Save frames of a video as JPEG images at a chosen frame rate.

    Frames are picked by timestamp: a frame is kept once its time reaches the
    next scheduled output time, then the schedule advances by
    1 / effective frame rate. Images go in `output_dir/frames/`, and
    `output_dir/manifest.json` lists each one with its source frame number
    and timestamp.

    This runs inside the request rather than as a background job.

    Args:
        source_path: The video file.
        output_dir: Folder to create for the output. It must not exist yet.
        requested_fps: Target frame rate. Capped at the video's own rate.
        output_width: Resize frames to this width. Give both or neither.
        output_height: Resize frames to this height. Give both or neither.

    Returns:
        A summary of what was written.

    Raises:
        ValueError: If the extension, frame rate or dimensions are invalid,
            or the video cannot be read.
        FileExistsError: If `output_dir` already exists.
        RuntimeError: If a frame cannot be written or no frames were read.
    """
    if source_path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError(f"Unsupported video extension: {source_path.suffix}")
    if requested_fps <= 0 or not math.isfinite(requested_fps):
        raise ValueError("fps must be a positive finite number")
    if (output_width is None) != (output_height is None):
        raise ValueError("output_width and output_height must be provided together")
    if output_width is not None and (output_width <= 0 or output_height <= 0):
        raise ValueError("Output dimensions must be positive")

    metadata = inspect_video(source_path)
    effective_fps = min(requested_fps, metadata.fps)
    output_dir.mkdir(parents=True, exist_ok=False)
    frames_dir = output_dir / "frames"
    frames_dir.mkdir()

    capture = cv2.VideoCapture(str(source_path))
    manifest: list[dict[str, int | str | float]] = []
    next_output_time = 0.0
    frame_number = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok or frame is None:
                break

            timestamp_ms = capture.get(cv2.CAP_PROP_POS_MSEC)
            if timestamp_ms < 0:
                timestamp_ms = frame_number / metadata.fps * 1000
            timestamp_seconds = timestamp_ms / 1000
            if timestamp_seconds + 1e-9 < next_output_time:
                frame_number += 1
                continue

            if output_width is not None:
                frame = cv2.resize(frame, (output_width, output_height), interpolation=cv2.INTER_AREA)
            frame_name = f"frame_{len(manifest):06d}.jpg"
            frame_path = frames_dir / frame_name
            if not cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                raise RuntimeError(f"Could not write extracted frame {frame_name}")
            manifest.append({
                "index": len(manifest),
                "source_frame_number": frame_number,
                "timestamp_ms": round(timestamp_ms, 3),
                "path": f"frames/{frame_name}",
            })
            next_output_time += 1 / effective_fps
            frame_number += 1
    finally:
        capture.release()

    if not manifest:
        raise RuntimeError("Video did not yield any frames")

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps({
        "schema_version": "1.0",
        "source": {
            "width": metadata.width,
            "height": metadata.height,
            "fps": metadata.fps,
            "frame_count": metadata.frame_count,
            "duration_seconds": metadata.duration_seconds,
        },
        "requested_fps": requested_fps,
        "effective_fps": effective_fps,
        "output_width": output_width or metadata.width,
        "output_height": output_height or metadata.height,
        "frames": manifest,
    }, indent=2), encoding="utf-8")

    digest = hashlib.sha256()
    total_size = 0
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            total_size += path.stat().st_size
            digest.update(path.relative_to(output_dir).as_posix().encode())
            digest.update(path.read_bytes())

    return FrameExtractionResult(
        metadata=metadata,
        requested_fps=requested_fps,
        effective_fps=effective_fps,
        frame_count=len(manifest),
        manifest_path=manifest_path,
        output_size_bytes=total_size,
        checksum_sha256=digest.hexdigest(),
    )