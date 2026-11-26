"""Detection of subjects as small bright spots inside the arena.

Each frame is masked to the arena, thresholded relative to its own brightest
pixel, and split into blobs. A blob counts as a subject if its size and shape
pass a set of filters. See [Subject detection](../pipeline/detection.md).
"""

from __future__ import annotations

import base64
import math
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from app.cv.plate_detection import find_plate, mask_frame_by_circle


def detect_small_bright_spots(
    frame: np.ndarray,
    min_area: float = 50.0,
    max_area: float = 1000.0,
    brightness_ratio: float = 0.85,
    min_solidity: float = 0.80,
    min_aspect_ratio: float = 0.5,
    max_aspect_ratio: float = 2.0,
    min_circularity: float = 0.50,
) -> list[tuple[int, int]]:
    """Find subject positions in one frame.

    The frame is converted to grayscale and lightly blurred (3x3 Gaussian).
    Pixels brighter than `brightness_ratio` times the frame's brightest pixel
    become foreground, and each connected region is a candidate blob. A blob
    is kept if all of these hold:

    - its area is between `min_area` and `max_area`;
    - its solidity (area divided by convex hull area) is above `min_solidity`;
    - its bounding box's width-to-height ratio is between `min_aspect_ratio`
      and `max_aspect_ratio`;
    - its circularity (4π × area / perimeter²) is above `min_circularity`.

    Args:
        frame: A color (BGR) frame, usually already masked to the arena.
        min_area: Smallest blob area, in square pixels.
        max_area: Largest blob area, in square pixels. Note the default here
            (1000) is larger than the default used by `detect_subjects` (250).
        brightness_ratio: Threshold as a fraction of the frame's brightest
            pixel. Because it is relative, the threshold changes from frame to
            frame with the brightest object in view.
        min_solidity: Lowest accepted solidity, from 0 to 1.
        min_aspect_ratio: Lowest accepted width-to-height ratio.
        max_aspect_ratio: Highest accepted width-to-height ratio.
        min_circularity: Lowest accepted circularity, from 0 to 1.

    Returns:
        The center of each accepted blob, from its image moments, rounded
        down to whole pixels.
    """
    gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (3, 3), sigmaX=0, sigmaY=0)
    _, thresh = cv2.threshold(gray, np.max(gray) * brightness_ratio, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    points: list[tuple[int, int]] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if not min_area <= area <= max_area:
            continue
        hull_area = cv2.contourArea(cv2.convexHull(contour))
        perimeter = cv2.arcLength(contour, True)
        if hull_area == 0 or perimeter == 0:
            continue
        _, _, width, height = cv2.boundingRect(contour)
        solidity = area / hull_area
        aspect_ratio = width / height
        circularity = 4 * math.pi * area / (perimeter * perimeter)
        if solidity > min_solidity and min_aspect_ratio <= aspect_ratio <= max_aspect_ratio and circularity > min_circularity:
            m = cv2.moments(contour)
            if m["m00"] != 0:
                points.append((int(m["m10"] / m["m00"]), int(m["m01"] / m["m00"])))
            else:
                points.append((int(contour[0][0][0]), int(contour[0][0][1])))
    return points


def detect_subjects(
    video_path: str,
    start_frame: int = 0,
    number_of_frames: int | None = None,
    min_area: float = 50.0,
    max_area: float = 250.0,
    brightness_ratio: float = 0.85,
    frame_step: int = 1,
    min_solidity: float = 0.80,
    min_aspect_ratio: float = 0.5,
    max_aspect_ratio: float = 2.0,
    min_circularity: float = 0.50,
    plate_cx: int | None = None,
    plate_cy: int | None = None,
    plate_r: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Detect subjects in every sampled frame of a video.

    The arena is detected once from the first frames, unless all three
    `plate_*` values are given. Frames are then read from `start_frame`, and
    every `frame_step`-th frame is masked to the arena and passed to
    `detect_small_bright_spots`.

    The returned dictionary has:

    - `points`: detections per frame, keyed by **sample index** (0, 1, 2,
      …), not by the video's own frame number. With `frame_step` 1 the two
      are the same.
    - `plate`: the arena as (center x, center y, radius).
    - `fps`: the effective frame rate (video frame rate divided by
      `frame_step`), or None if the video reports none.
    - `frame_count`: number of sampled frames.

    Args:
        video_path: The video file.
        start_frame: First frame to read.
        number_of_frames: Most frames to read, or None for the whole video.
        min_area: See `detect_small_bright_spots`.
        max_area: See `detect_small_bright_spots`.
        brightness_ratio: See `detect_small_bright_spots`.
        frame_step: Process one frame in every `frame_step`, to lower the
            effective frame rate.
        min_solidity: See `detect_small_bright_spots`.
        min_aspect_ratio: See `detect_small_bright_spots`.
        max_aspect_ratio: See `detect_small_bright_spots`.
        min_circularity: See `detect_small_bright_spots`.
        plate_cx: Manual arena center x, overriding detection.
        plate_cy: Manual arena center y, overriding detection.
        plate_r: Manual arena radius, overriding detection.
        on_progress: Optional callback, called with (frames done, total frames)
            every 50 sampled frames and at the end.

    Returns:
        The detections and arena, as described above.

    Raises:
        RuntimeError: If the video cannot be opened, the arena cannot be
            found, or no frames can be read.
    """
    cap = cv2.VideoCapture(video_path)
    try:
        if not cap.isOpened():
            raise RuntimeError("Could not open video")
        native_fps = cap.get(cv2.CAP_PROP_FPS)
        total_raw = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if number_of_frames is not None:
            total_raw = min(number_of_frames, total_raw)
        total_sampled = max(1, math.ceil(total_raw / frame_step))
        if plate_cx is not None and plate_cy is not None and plate_r is not None:
            h, k, r = plate_cx, plate_cy, plate_r
        else:
            h, k, r = (int(v) for v in find_plate(cap))
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        points: dict[int, list[tuple[int, int]]] = {}
        raw_index = 0
        sampled_index = 0
        while number_of_frames is None or raw_index < number_of_frames:
            ok, frame = cap.read()
            if not ok:
                break
            if raw_index % frame_step == 0:
                interior = mask_frame_by_circle(frame, (h, k), r)
                points[sampled_index] = detect_small_bright_spots(
                    interior, min_area, max_area, brightness_ratio,
                    min_solidity, min_aspect_ratio, max_aspect_ratio, min_circularity,
                )
                sampled_index += 1
                if on_progress and sampled_index % 50 == 0:
                    on_progress(sampled_index, total_sampled)
            raw_index += 1
        if on_progress:
            on_progress(sampled_index, total_sampled)
    finally:
        cap.release()

    if not points:
        raise RuntimeError(f"No frames could be read from start_frame={start_frame}")
    effective_fps = (native_fps / frame_step) if native_fps and native_fps > 0 else None
    return {"points": points, "plate": (h, k, r), "fps": effective_fps, "frame_count": len(points)}


def analyze_frame_detections(
    video_path: str | Path,
    frame_index: int,
    min_area: float = 50.0,
    max_area: float = 250.0,
    brightness_ratio: float = 0.85,
    min_solidity: float = 0.80,
    min_aspect_ratio: float = 0.5,
    max_aspect_ratio: float = 2.0,
    min_circularity: float = 0.50,
    plate_cx: int | None = None,
    plate_cy: int | None = None,
    plate_r: int | None = None,
) -> dict:
    """Run detection on one frame and explain every decision.

    This powers the live preview in the Subject Detection step. Unlike
    `detect_small_bright_spots`, it reports every blob, including rejected
    ones and the reason each was rejected, and returns images for display.

    The returned dictionary has:

    - `plate`: the arena as `cx`, `cy` and `r`.
    - `spots`: one entry per blob, with its position, area, shape measures,
      whether it was `accepted`, and a `reject` reason (`too_small`,
      `too_large`, `degenerate`, `not_solid`, `wrong_aspect` or
      `not_circular`). Shape measures are None for blobs rejected before
      they were measured.
    - `brightness_threshold`: the absolute threshold used.
    - `max_pixel`: the frame's brightest pixel after masking and blurring.
    - `bw_image`: the thresholded image with the arena and blobs outlined,
      as base64 JPEG.
    - `annotated_image`: the original frame with the same overlays, as
      base64 JPEG. Accepted blobs are green and rejected ones red.

    Args:
        video_path: The video file.
        frame_index: The frame to analyze.
        min_area: See `detect_small_bright_spots`.
        max_area: See `detect_small_bright_spots`.
        brightness_ratio: See `detect_small_bright_spots`.
        min_solidity: See `detect_small_bright_spots`.
        min_aspect_ratio: See `detect_small_bright_spots`.
        max_aspect_ratio: See `detect_small_bright_spots`.
        min_circularity: See `detect_small_bright_spots`.
        plate_cx: Manual arena center x, overriding detection.
        plate_cy: Manual arena center y, overriding detection.
        plate_r: Manual arena radius, overriding detection.

    Returns:
        The analysis and images, as described above.

    Raises:
        ValueError: If the video cannot be opened or the frame cannot be read.
        RuntimeError: If the arena cannot be found.
    """
    cap = cv2.VideoCapture(str(video_path))
    try:
        if not cap.isOpened():
            raise ValueError("Could not open video")
        if plate_cx is not None and plate_cy is not None and plate_r is not None:
            h, k, r = plate_cx, plate_cy, plate_r
        else:
            h, k, r = (int(v) for v in find_plate(cap))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = cap.read()
        if not ok:
            raise ValueError(f"Could not read frame {frame_index}")
    finally:
        cap.release()

    interior = mask_frame_by_circle(frame, (h, k), r)
    gray = cv2.GaussianBlur(cv2.cvtColor(interior, cv2.COLOR_BGR2GRAY), (3, 3), sigmaX=0, sigmaY=0)
    max_gray = int(np.max(gray))
    thresh_abs = max_gray * brightness_ratio
    _, thresh = cv2.threshold(gray, thresh_abs, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    spots: list[dict] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        m = cv2.moments(contour)
        cx = int(m["m10"] / m["m00"]) if m["m00"] != 0 else int(contour[0][0][0])
        cy = int(m["m01"] / m["m00"]) if m["m00"] != 0 else int(contour[0][0][1])

        if area < min_area:
            reject = "too_small"
        elif area > max_area:
            reject = "too_large"
        else:
            hull_area = cv2.contourArea(cv2.convexHull(contour))
            perimeter = cv2.arcLength(contour, True)
            if hull_area == 0 or perimeter == 0:
                reject = "degenerate"
            else:
                _, _, w, bh = cv2.boundingRect(contour)
                solidity = area / hull_area
                aspect = w / bh
                circ = 4 * math.pi * area / (perimeter * perimeter)
                if solidity <= min_solidity:
                    reject = "not_solid"
                elif not (min_aspect_ratio <= aspect <= max_aspect_ratio):
                    reject = "wrong_aspect"
                elif circ <= min_circularity:
                    reject = "not_circular"
                else:
                    reject = None

        spots.append({
            "x": cx, "y": cy, "area": round(float(area), 1),
            "solidity": round(float(solidity), 3) if reject not in ("too_small", "too_large", "degenerate") else None,
            "aspect_ratio": round(float(aspect), 3) if reject not in ("too_small", "too_large", "degenerate") else None,
            "circularity": round(float(circ), 3) if reject not in ("too_small", "too_large", "degenerate") else None,
            "accepted": reject is None, "reject": reject,
        })

    # BW view: white = above threshold, black = below; plate circle + spot rings overlaid
    bw_bgr = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)
    cv2.circle(bw_bgr, (h, k), r, (80, 200, 80), 2)
    for s in spots:
        color = (91, 242, 53) if s["accepted"] else (80, 80, 220)
        cv2.circle(bw_bgr, (s["x"], s["y"]), 9, color, 1)

    # Annotated color view
    ann = frame.copy()
    cv2.circle(ann, (h, k), r, (80, 200, 80), 2)
    for s in spots:
        color = (91, 242, 53) if s["accepted"] else (80, 80, 220)
        cv2.circle(ann, (s["x"], s["y"]), 8, color, 2)
        cv2.circle(ann, (s["x"], s["y"]), 2, color, -1)

    def _jpg_b64(img: np.ndarray) -> str:
        _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
        return base64.b64encode(buf.tobytes()).decode()

    return {
        "plate": {"cx": h, "cy": k, "r": r},
        "spots": spots,
        "brightness_threshold": round(float(thresh_abs), 1),
        "max_pixel": max_gray,
        "bw_image": _jpg_b64(bw_bgr),
        "annotated_image": _jpg_b64(ann),
    }

