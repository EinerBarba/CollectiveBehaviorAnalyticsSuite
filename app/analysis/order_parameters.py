"""Order parameters that describe a group's collective state over time.

The video is cut into overlapping windows of frames. For each window the
module measures how aligned the subjects are (P, P_local), how much they
circle the arena center (M), and how well the group follows the light
stimulus (S). See [Collective behavior](../pipeline/collective-behavior.md)
for the definitions in plain language.

All headings are unit vectors from one detected position to the next, so
speed plays no part in any of these measures.
"""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np
import pandas as pd

WINDOW_SIZE = 100
"""Default window length, in frames."""

WINDOW_STEP = 50
"""Default distance between window starts, in frames. With the default size,
neighboring windows overlap by half."""

MIN_VALID_FRACTION = 0.5
"""A window is skipped if fewer than this share of its expected points were
detected. The expected count is the window's group size times its length."""

_DEFAULT_WINDOW_SIZE = WINDOW_SIZE
_DEFAULT_WINDOW_STEP = WINDOW_STEP


class StimulusParams(NamedTuple):
    """The rotating light's motion, as needed to compute S.

    Attributes:
        omega: Angular speed in degrees per frame. Positive means increasing
            angle, which is clockwise on screen because image y points down.
        theta_light_0: The light's angle at frame 0, in degrees.
    """

    omega: float          # deg/frame, signed (positive = clockwise in OpenCV pixel space)
    theta_light_0: float  # initial LED phase in degrees


def _compute_headings(df: pd.DataFrame) -> pd.DataFrame:
    """Compute each subject's heading between consecutive detected points.

    Predicted points are dropped first, so a heading may span several frames
    if a track had a gap. Steps of zero length have no heading and are left
    out. Each heading is assigned to the later of its two frames.

    Args:
        df: Track points with `track_id`, `frame`, `x`, `y` and `is_predicted`.

    Returns:
        One row per heading, with `track_id`, `frame`, `x`, `y` (the later
        position) and the unit vector `ux`, `uy`.
    """
    rows: list[tuple] = []
    for track_id, grp in df.groupby("track_id", sort=False):
        observed = grp[~grp["is_predicted"]].sort_values("frame")
        pts = observed[["frame", "x", "y"]].to_numpy(dtype=float)
        for i in range(1, len(pts)):
            f_cur, x_cur, y_cur = pts[i]
            _, x_prev, y_prev = pts[i - 1]
            dx, dy = x_cur - x_prev, y_cur - y_prev
            mag = math.hypot(dx, dy)
            if mag > 0:
                rows.append((track_id, int(f_cur), x_cur, y_cur, dx / mag, dy / mag))
    if not rows:
        return pd.DataFrame(columns=["track_id", "frame", "x", "y", "ux", "uy"])
    return pd.DataFrame(rows, columns=["track_id", "frame", "x", "y", "ux", "uy"])


def _sliding_windows(
    f_min: int,
    f_max: int,
    window_size: int = _DEFAULT_WINDOW_SIZE,
    window_step: int = _DEFAULT_WINDOW_STEP,
) -> list[tuple[int, int, int]]:
    """List the windows covering a range of frames.

    Only whole windows are produced, so frames after the last full window are
    not analyzed.

    Returns:
        (index, first frame, frame after the last) for each window.
    """
    windows: list[tuple[int, int, int]] = []
    t = f_min
    idx = 0
    while t + window_size <= f_max + 1:
        windows.append((idx, t, t + window_size))
        t += window_step
        idx += 1
    return windows


def compute_window_features(
    df: pd.DataFrame,
    arena_center: tuple[float, float],
    arena_radius: float,
    stimulus: StimulusParams | None,
    video_id: str,
    startup_threshold: int | None = None,
    window_size: int = _DEFAULT_WINDOW_SIZE,
    window_step: int = _DEFAULT_WINDOW_STEP,
) -> list[dict]:
    """Compute the order parameters for every usable window of one video.

    A window is skipped if it starts before `startup_threshold`, if fewer
    than `MIN_VALID_FRACTION` of its expected points were detected, or if it
    contains no headings. Within a window, each measure is first computed per
    frame and then averaged over the window's frames:

    - **P (polarization).** Length of the mean heading vector of all subjects
      in the frame. 1 means all move the same way; near 0 means no common
      direction.
    - **P_local (local polarization).** The arena is split into 8 equal
      angular sectors around its center. For each occupied sector, P is
      computed from the subjects in it, or 0 if it holds only one. The
      frame's value is the mean over occupied sectors.
    - **M (milling).** For each subject, the cross product of its position
      relative to the arena center with its heading, divided by the arena
      radius. This is positive for one direction of circling and negative for
      the other. M is the absolute value of the frame's mean, so it measures
      circling regardless of direction. `M_signed` keeps the direction.
    - **S (stimulus alignment).** Only with a stimulus. The light's angular
      position is `theta_light_0 + omega × frame`, and the target is the
      light's direction of travel at that position: its angle plus 90° in the
      direction of rotation. S is the cosine of the angle between the group's
      mean heading and that target: 1 means moving the way the light moves,
      -1 the opposite way. This is one global direction for the whole group,
      not relative to each subject's own position. NaN without a stimulus.

    Args:
        df: Track points with `track_id`, `frame`, `x`, `y` and `is_predicted`.
        arena_center: Arena center (x, y) in pixels.
        arena_radius: Arena radius in pixels, used to scale M.
        stimulus: The light's motion, or None if there is no stimulus or it
            does not move.
        video_id: Label copied into every output row.
        startup_threshold: Skip windows that start before this frame, for
            example before the light switches on. None skips nothing.
        window_size: Window length in frames.
        window_step: Distance between window starts in frames.

    Returns:
        One dictionary per kept window, with `video_id`, `window_index`,
        `t_start`, `t_end`, `N` (most subjects detected in any frame of the
        window), `valid_fraction`, `P`, `P_local`, `M`, `M_signed` and `S`.
    """
    cx, cy = arena_center
    headings = _compute_headings(df)

    all_frames = df["frame"].to_numpy(dtype=int)
    if len(all_frames) == 0:
        return []
    f_min, f_max = int(all_frames.min()), int(all_frames.max())
    windows = _sliding_windows(f_min, f_max, window_size=window_size, window_step=window_step)
    if not windows:
        return []

    non_pred_per_frame: dict[int, int] = (
        df[~df["is_predicted"]].groupby("frame").size().to_dict()
    )

    # Compute cross-product
    if not headings.empty:
        headings = headings.copy()
        headings["cross"] = (
            (headings["x"] - cx) * headings["uy"]
            - (headings["y"] - cy) * headings["ux"]
        ) / arena_radius

    has_stimulus = stimulus is not None and stimulus.omega != 0.0
    if has_stimulus:
        omega = float(stimulus.omega)         
        theta0 = float(stimulus.theta_light_0)
        sgn = math.copysign(1.0, omega)

    features: list[dict] = []
    for win_idx, t_start, t_end in windows:
        if startup_threshold is not None and t_start < startup_threshold:
            continue
        window_obs = [non_pred_per_frame.get(f, 0) for f in range(t_start, t_end)]
        n_obs = sum(window_obs)
        N_window = max(window_obs) if window_obs else 0
        expected = N_window * window_size
        valid_fraction = n_obs / expected if expected > 0 else 0.0
        if valid_fraction < MIN_VALID_FRACTION:
            continue

        wh = headings[
            (headings["frame"] >= t_start) & (headings["frame"] < t_end)
        ]
        if wh.empty:
            continue

        grp = wh.groupby("frame", sort=True)
        mean_ux = grp["ux"].mean()
        mean_uy = grp["uy"].mean()
        m_signed_per_frame = grp["cross"].mean()

        frames_arr = mean_ux.index.to_numpy(dtype=float)
        ux_arr = mean_ux.to_numpy()
        uy_arr = mean_uy.to_numpy()

        P_arr = np.hypot(ux_arr, uy_arr)
        M_signed_arr = m_signed_per_frame.to_numpy()
        M_arr = np.abs(M_signed_arr)

        P_window = float(P_arr.mean())

        wh_x = wh["x"].to_numpy()
        wh_y = wh["y"].to_numpy()
        wh_ux = wh["ux"].to_numpy()
        wh_uy = wh["uy"].to_numpy()
        wh_frames = wh["frame"].to_numpy(dtype=int)
        wh_angles = np.arctan2(wh_y - cy, wh_x - cx)
        wh_sectors = (np.floor((wh_angles + np.pi) * 4.0 / np.pi).astype(int)) % 8
        p_local_frames = []
        for f in np.unique(wh_frames):
            f_mask = wh_frames == f
            f_sectors = wh_sectors[f_mask]
            f_ux = wh_ux[f_mask]
            f_uy = wh_uy[f_mask]
            f_counts = np.bincount(f_sectors, minlength=8)
            p_local_frames.append(float(np.mean([
                np.hypot(f_ux[f_sectors == s].mean(), f_uy[f_sectors == s].mean())
                if f_counts[s] >= 2 else 0.0
                for s in np.unique(f_sectors)
            ])))
        P_local_window = float(np.mean(p_local_frames)) if p_local_frames else float("nan")

        M_window = float(M_arr.mean())
        M_signed_window = float(M_signed_arr.mean())

        S_window = float("nan")
        if has_stimulus:
            theta_light = (theta0 + omega * frames_arr) % 360.0
            theta_stim = theta_light + 90.0 * sgn
            theta_group = np.degrees(np.arctan2(uy_arr, ux_arr))
            delta = (theta_group - theta_stim + 180.0) % 360.0 - 180.0
            S_window = float(np.cos(np.radians(delta)).mean())

        features.append(
            {
                "video_id": video_id,
                "window_index": win_idx,
                "t_start": t_start,
                "t_end": t_end,
                "N": N_window,
                "valid_fraction": valid_fraction,
                "P": P_window,
                "P_local": P_local_window,
                "M": M_window,
                "M_signed": M_signed_window,
                "S": S_window,
            }
        )

    return features
