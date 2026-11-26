"""A Markov model of how the group moves between behavioral states.

The sequence of state labels from `app.analysis.clustering` is treated as a
first-order Markov chain: the next state depends only on the current one.
See [Collective behavior](../pipeline/collective-behavior.md).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

def build_transition_matrix(windows: pd.DataFrame, k: int = 3) -> np.ndarray:
    """Estimate the probability of moving from each state to each other state.

    Transitions are counted between consecutive clustered windows of the same
    video, in window order. Windows skipped earlier do not break the
    sequence, so a transition may join two windows that were not adjacent in
    time. Videos are never joined to each other. Every count starts at 1
    (add-one smoothing), so no transition has probability exactly 0.

    Args:
        windows: Labeled windows, with `video_id`, `window_index`, `state`
            and `included_in_clustering`.
        k: Number of states.

    Returns:
        A k-by-k matrix whose row i holds the probabilities of moving from
        state i to each state. Each row sums to 1.
    """
    counts = np.ones((k, k), dtype=float)

    for _, video_windows in windows[windows["included_in_clustering"]].groupby("video_id"):
        states = video_windows.sort_values("window_index")["state"].to_numpy()
        for s_from, s_to in zip(states[:-1], states[1:]):
            counts[s_from, s_to] += 1.0

    row_sums = counts.sum(axis=1, keepdims=True)
    T = counts / row_sums
    return T


def stationary_distribution(T: np.ndarray) -> np.ndarray:
    """Find the long-run share of time spent in each state.

    This is the distribution that the transition matrix leaves unchanged,
    found as the eigenvector for the eigenvalue closest to 1.

    Args:
        T: The transition matrix.

    Returns:
        One share per state, summing to 1.
    """
    # Solve π T = π  ↔  (T^T - I) π^T = 0
    eigenvalues, eigenvectors = np.linalg.eig(T.T)
    # Eigenvector corresponding to eigenvalue closest to 1
    idx = int(np.argmin(np.abs(eigenvalues - 1.0)))
    pi = eigenvectors[:, idx].real
    pi = np.abs(pi)
    pi /= pi.sum()
    return pi


def mean_dwell_times(T: np.ndarray, window_step_seconds: float) -> np.ndarray:
    """Expected time the group stays in each state once it enters it.

    For a Markov chain this is 1 / (1 − p), where p is the probability of
    staying in the state from one window to the next. It assumes dwell times
    follow a geometric distribution.

    Args:
        T: The transition matrix.
        window_step_seconds: Time between window starts, in seconds.

    Returns:
        Mean dwell time per state, in seconds. Infinite for a state that is
        never left.
    """
    diag = np.diag(T)
    denom = np.where(diag < 1.0, 1.0 - diag, np.nan)
    dwell_windows = np.where(np.isnan(denom), np.inf, 1.0 / denom)
    return dwell_windows * window_step_seconds


def compute_dwell_runs(windows: pd.DataFrame, window_step_seconds: float) -> pd.DataFrame:
    """List every observed stay in a state.

    Unlike `mean_dwell_times`, which comes from the model, these are the
    actual runs of identical consecutive labels in each video.

    Args:
        windows: Labeled windows.
        window_step_seconds: Time between window starts, in seconds.

    Returns:
        One row per run, with `state`, `length_windows`, `length_seconds` and
        `video_id`.
    """
    rows: list[dict] = []
    for video_id, vw in windows[windows["included_in_clustering"]].groupby("video_id"):
        states = vw.sort_values("window_index")["state"].to_numpy()
        if len(states) == 0:
            continue
        current_state = states[0]
        run_len = 1
        for s in states[1:]:
            if s == current_state:
                run_len += 1
            else:
                rows.append(
                    {
                        "state": int(current_state),
                        "length_windows": run_len,
                        "length_seconds": run_len * window_step_seconds,
                        "video_id": video_id,
                    }
                )
                current_state = s
                run_len = 1
        rows.append(
            {
                "state": int(current_state),
                "length_windows": run_len,
                "length_seconds": run_len * window_step_seconds,
                "video_id": video_id,
            }
        )
    return pd.DataFrame(rows)


def markov_summary(
    T: np.ndarray,
    pi: np.ndarray,
    dwell_secs: np.ndarray,
    windows: pd.DataFrame,
) -> dict:
    """Collect the model's headline numbers for `markov_summary.json`.

    Args:
        T: The transition matrix. Not included in the output here; the
            experiment-level analysis adds it afterwards.
        pi: The stationary distribution.
        dwell_secs: Mean dwell time per state, in seconds.
        windows: Labeled windows.

    Returns:
        A dictionary with `mean_dwell_seconds`, `stationary_distribution`,
        `total_transitions` and `total_windows_clustered`.
    """
    total_transitions = int(
        windows[windows["included_in_clustering"]].groupby("video_id")
        .apply(lambda g: max(0, len(g) - 1))
        .sum()
    )
    total_windows_clustered = int(windows["included_in_clustering"].sum())
    return {
        "mean_dwell_seconds": dwell_secs.tolist(),
        "stationary_distribution": pi.tolist(),
        "total_transitions": total_transitions,
        "total_windows_clustered": total_windows_clustered,
    }
