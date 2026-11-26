"""Detection of the circular arena (the plate) in a video.

The arena is found once per video, from its first frames, and everything
outside it is masked before subjects are detected. See
[Subject detection](../pipeline/detection.md).
"""

import cv2
import numpy as np


def bg_preprocess(frame: np.ndarray) -> np.ndarray:
    """Prepare a frame so the arena's edge stands out for circle detection.

    Bright objects such as the subjects and the light would otherwise create
    false edges. Pixels brighter than 80% of the frame's maximum are replaced
    with mid-gray. Contrast is then tripled around mid-gray, the result is
    clipped to the range 92 to 255 and stretched to the full 0 to 255 range,
    and the frame is converted to grayscale.

    Args:
        frame: A color (BGR) video frame.

    Returns:
        The processed grayscale image.
    """
    processed_frame = frame.copy()

    # 1. Find the brightest value in grayscale
    temp_gray = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2GRAY)
    max_val = np.max(temp_gray)
    threshold_val = max_val * 0.8

    # 2. Create a mask for the brightest pixels (top 20%)
    _, bright_mask = cv2.threshold(temp_gray, threshold_val, 255, cv2.THRESH_BINARY)

    # 3. Replace the bright markers with the black_point value
    # This blends them into the background to avoid false edge detection
    black_point = 128
    processed_frame[bright_mask == 255] = (black_point, black_point, black_point)

    # 4. Apply maximized contrast and normalize
    contrast = 3.0
    frame_norm = np.clip((processed_frame.astype(np.float32) - black_point) * contrast, 92, 255).astype(np.uint8)
    frame_norm = cv2.normalize(frame_norm, None, 0, 255, cv2.NORM_MINMAX)

    # 5. Convert back to grayscale for the final output
    gray = cv2.cvtColor(frame_norm, cv2.COLOR_BGR2GRAY)
    cv2.medianBlur(gray, 1)
    return gray


def possible_plates(frame: np.ndarray) -> list[tuple[int, int, int]]:
    """Find candidate arena circles in one frame.

    Uses the Hough circle transform on the preprocessed frame. Candidates must
    have a radius between 30% and 50% of the frame's shorter side, lie at
    least 10% of that side apart, and fit entirely inside the frame.

    Args:
        frame: A color (BGR) video frame.

    Returns:
        Candidate circles as (center x, center y, radius) in pixels, largest
        first. Empty if none were found.
    """
    # 1. convert to gray scale
    gray = bg_preprocess(frame)

    # 3. Apply the Hough Circle Transform
    rows, cols = gray.shape
    min_size = min(rows, cols)
    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=min_size * 0.1,
        param1=70,
        param2=40,
        minRadius=int(min_size * 0.30),
        maxRadius=int(min_size * 0.50),
    )

    if circles is not None:
        circles = np.uint16(np.around(circles[0, :]))
        valid_circles = [
            (h, k, r) for h, k, r in circles
            if h >= r and h + r <= cols and k >= r and k + r <= rows
        ]
        circles_sorted = sorted(valid_circles, key=lambda c: c[2], reverse=True)
        return circles_sorted
    else:
        return []


def mask_frame_by_circle(frame: np.ndarray, circle_center: tuple[int, int], circle_radius: int) -> np.ndarray:
    """Black out everything outside a circle.

    Args:
        frame: A video frame.
        circle_center: The circle's center (x, y) in pixels.
        circle_radius: The circle's radius in pixels.

    Returns:
        A copy of the frame with pixels outside the circle set to zero.
    """
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    cv2.circle(mask, circle_center, circle_radius, 255, -1)
    result = cv2.bitwise_and(frame, frame, mask=mask)
    return result


def find_plate(cap: cv2.VideoCapture, max_probe_frames: int = 30) -> tuple[int, int, int]:
    """Find the arena in the first frames read from a video.

    Frames are read one at a time from the capture's current position. The
    first frame that yields any candidate wins, and its largest candidate is
    returned. Reading advances the capture, so callers seek afterwards.

    Args:
        cap: An open video capture.
        max_probe_frames: Most frames to try before giving up.

    Returns:
        The arena as (center x, center y, radius) in pixels.

    Raises:
        RuntimeError: If no candidate is found in the probed frames.
    """
    for _ in range(max_probe_frames):
        ret, frame = cap.read()
        if not ret:
            break
        plates = possible_plates(frame)
        if plates:
            return plates[0]
    raise RuntimeError("Could not detect the plate/arena circle in the first frames of the video")
