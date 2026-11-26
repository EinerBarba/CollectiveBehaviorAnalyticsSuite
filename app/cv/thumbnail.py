"""Video thumbnails for the experiment's video list."""

from pathlib import Path

import cv2
import numpy as np


def extract_thumbnail(video_path: Path, width: int = 480, height: int = 270) -> bytes:
    """Make a JPEG thumbnail from the middle frame of a video.

    The frame is scaled to fit inside `width` by `height` without changing its
    shape, and centered on a black background of exactly that size.

    Args:
        video_path: The video file.
        width: Thumbnail width in pixels.
        height: Thumbnail height in pixels.

    Returns:
        The JPEG bytes.

    Raises:
        ValueError: If no frame can be read or the image cannot be encoded.
    """
    cap = cv2.VideoCapture(str(video_path))
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total // 2))
        ok, frame = cap.read()
        if not ok or frame is None:
            raise ValueError("Could not read frame from video")
    finally:
        cap.release()

    h, w = frame.shape[:2]
    scale = min(width / w, height / h)
    nw, nh = int(w * scale), int(h * scale)
    resized = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)

    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    ox, oy = (width - nw) // 2, (height - nh) // 2
    canvas[oy:oy + nh, ox:ox + nw] = resized

    ok, buf = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        raise ValueError("Could not encode thumbnail")
    return bytes(buf)
