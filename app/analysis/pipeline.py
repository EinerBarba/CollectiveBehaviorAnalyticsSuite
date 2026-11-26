"""Offline, multi-video version of the collective-behavior analysis.

`run_pipeline` runs every analysis step on a list of videos and writes the
results, plus a text evaluation report, to a folder. The web application
does not call it; the jobs in `app.jobs.collective_behavior_job` run the same
steps instead. It is useful for running the analysis from a script.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import silhouette_score

from app.analysis.clustering import (
    FEATURES,
    assign_states,
    fit_gmm_models,
    select_best_k,
)
from app.analysis.markov import (
    build_transition_matrix,
    compute_dwell_runs,
    markov_summary,
    mean_dwell_times,
    stationary_distribution,
)
from app.analysis.order_parameters import StimulusParams, compute_window_features

N_DENSITY_BINS = [(5, 8), (9, 14), (15, 20)]
"""Group-size ranges used to break down the evaluation report."""

# Feature Matrix
def _build_feature_matrix(videos: list[dict]) -> pd.DataFrame:
    all_rows: list[dict] = []
    for v in videos:
        rows = compute_window_features(
            df=v["tracks_df"],
            arena_center=v["arena_center"],
            arena_radius=float(v["arena_radius"]),
            stimulus=v.get("stimulus"),
            video_id=v["video_id"],
        )
        all_rows.extend(rows)

    windows = pd.DataFrame(all_rows)
    if windows.empty:
        raise ValueError("No valid windows produced — check input data.")

    # S_normalized: rescale [-1, 1] → [0, 1]
    windows["S_normalized"] = (windows["S"] + 1.0) / 2.0
    windows["included_in_clustering"] = windows["N"] >= 5
    return windows

# Clustering
def _cluster(windows: pd.DataFrame):
    models, bic_df = fit_gmm_models(windows)
    best_k = select_best_k(models, bic_df)
    best_gmm = models[best_k][0]
    windows = assign_states(windows, best_gmm)
    return windows, best_gmm, bic_df, best_k

# Markov
def _markov(windows: pd.DataFrame, k: int, window_step_seconds: float = 5.0):
    T = build_transition_matrix(windows, k)
    pi = stationary_distribution(T)
    dwell_secs = mean_dwell_times(T, window_step_seconds)
    dwell_runs = compute_dwell_runs(windows, window_step_seconds)
    summary = markov_summary(T, pi, dwell_secs, windows)
    return T, pi, dwell_secs, dwell_runs, summary

def _sanity_checks(windows: pd.DataFrame, k: int) -> list[str]:
    """Flag results that suggest something went wrong.

    These are rough plausibility checks, not statistical tests. A FAIL is
    reported if one state holds over 90% of windows, mean S is near 0, mean
    P or P_local is above 0.95, a state's mean run lasts one window or less,
    or mean M is near 0.

    Returns:
        One line per check, starting with `[OK]` or `[FAIL]`.
    """
    lines: list[str] = []
    clustered = windows[windows["included_in_clustering"]]

    # 1. No single state > 90% of clustered windows
    if not clustered.empty:
        state_frac = clustered["state"].value_counts(normalize=True)
        for state, frac in state_frac.items():
            flag = "FAIL" if frac > 0.9 else "OK"
            lines.append(f"[{flag}] State {state} fraction: {frac:.3f} (threshold 0.90)")

    # 2. Mean S not ≈ 0
    mean_s = windows["S"].dropna().mean()
    s_flag = "FAIL" if abs(mean_s) < 0.05 else "OK"
    lines.append(f"[{s_flag}] Mean S across all windows: {mean_s:.4f}")

    # 3. Mean P not ≈ 1
    mean_p = windows["P"].mean()
    p_flag = "FAIL" if mean_p > 0.95 else "OK"
    lines.append(f"[{p_flag}] Mean P across all windows: {mean_p:.4f}")

    mean_p_local = windows["P_local"].mean()
    p_local_flag = "FAIL" if mean_p_local > 0.95 else "OK"
    lines.append(f"[{p_local_flag}] Mean P_local across all windows: {mean_p_local:.4f}")

    # 4. Mean dwell time > 1 window step per state
    if not clustered.empty:
        for state in range(k):
            runs = _dwell_runs_for_state(windows, state)
            if len(runs) > 0:
                mean_dwell = np.mean(runs)
                flag = "FAIL" if mean_dwell <= 1.0 else "OK"
                lines.append(
                    f"[{flag}] Mean dwell run (windows) state {state}: {mean_dwell:.2f}"
                )

    # 5. Mean M not ≈ 0
    mean_m = windows["M"].mean()
    m_flag = "FAIL" if abs(mean_m) < 0.01 else "OK"
    lines.append(f"[{m_flag}] Mean M across all windows: {mean_m:.4f}")

    return lines


def _dwell_runs_for_state(windows: pd.DataFrame, state: int) -> list[int]:
    runs: list[int] = []
    clustered = windows[windows["included_in_clustering"]]
    for _, vw in clustered.groupby("video_id"):
        states = vw.sort_values("window_index")["state"].to_numpy()
        run = 0
        for s in states:
            if s == state:
                run += 1
            elif run > 0:
                runs.append(run)
                run = 0
        if run > 0:
            runs.append(run)
    return runs

# Evaluation
def _evaluation_report(
    windows: pd.DataFrame,
    gmm,
    k: int,
    T: np.ndarray,
    pi: np.ndarray,
    dwell_secs: np.ndarray,
    sanity_lines: list[str],
    window_step_seconds: float = 5.0,
) -> str:
    lines: list[str] = ["=" * 70, "COLLECTIVE BEHAVIOR ANALYSIS — EVALUATION REPORT", "=" * 70, ""]

    # Silhouette score
    clustered = windows[windows["included_in_clustering"]]
    X = clustered[FEATURES].fillna(0.5).to_numpy(dtype=float)
    labels = clustered["state"].to_numpy()
    try:
        sil = silhouette_score(X, labels) if len(np.unique(labels)) > 1 else float("nan")
    except Exception:
        sil = float("nan")
    lines.append(f"Selected k          : {k}")
    lines.append(f"Silhouette score    : {sil:.4f}")
    lines.append("")

    # GMM centroids
    lines.append("GMM centroids (P, P_local, M, S_normalized) — ordered by mean S:")
    # Reorder means by the same S ordering used in assign_states
    mean_s_per_component = np.array([
        clustered.loc[clustered["state"] == i, "S_normalized"].fillna(0.5).mean()
        for i in range(k)
    ])
    order = np.argsort(mean_s_per_component)
    for state_i, raw_c in enumerate(order):
        m = gmm.means_[raw_c]
        feature_str = ", ".join(f"{v:.4f}" for v in m)
        lines.append(f"  State {state_i} (raw component {raw_c}): [{feature_str}]")
    lines.append("")

    lines.append("Window fraction per state × density bin (N range):")
    header = f"  {'State':<8}" + "".join(f"  N={lo}–{hi}" for lo, hi in N_DENSITY_BINS)
    lines.append(header)
    for state in range(k):
        row = f"  {state:<8}"
        for lo, hi in N_DENSITY_BINS:
            bin_mask = (windows["N"] >= lo) & (windows["N"] <= hi)
            bin_windows = windows[bin_mask & windows["included_in_clustering"]]
            if bin_windows.empty:
                row += "       —  "
            else:
                frac = (bin_windows["state"] == state).mean()
                row += f"  {frac:.3f}   "
        lines.append(row)
    lines.append("")

    lines.append("Mean dwell time (seconds) per state × density bin:")
    lines.append(header)
    for state in range(k):
        row = f"  {state:<8}"
        for lo, hi in N_DENSITY_BINS:
            bin_mask = (windows["N"] >= lo) & (windows["N"] <= hi) & windows["included_in_clustering"]
            bin_windows = windows[bin_mask]
            runs = []
            for _, vw in bin_windows.groupby("video_id"):
                states = vw.sort_values("window_index")["state"].to_numpy()
                run = 0
                for s in states:
                    if s == state:
                        run += 1
                    elif run > 0:
                        runs.append(run)
                        run = 0
                if run > 0:
                    runs.append(run)
            if runs:
                row += f"  {np.mean(runs) * window_step_seconds:.1f}s  "
            else:
                row += "       —  "
        lines.append(row)
    lines.append("")

    lines.append("Sanity checks:")
    for sl in sanity_lines:
        lines.append(f"  {sl}")
        if sl.startswith("[FAIL]"):
            lines.append(f"  *** WARNING: sanity check failed — see above ***")
    lines.append("")

    return "\n".join(lines)


def run_pipeline(videos: list[dict], output_dir: Path, window_step_seconds: float = 5.0) -> dict:
    """Run the full analysis on several videos and save the results.

    Steps: order parameters per window, one mixture model fitted to all
    videos' windows together, state labels ordered by `S_normalized`, a
    Markov model, sanity checks and an evaluation report.

    The folder receives `windows.parquet`, `gmm_model.pkl`,
    `bic_scores.csv`, `transition_matrix.csv`, `markov_summary.json`,
    `dwell_runs.parquet` and `evaluation_report.txt`.

    Args:
        videos: One dictionary per video, with `tracks_df` (track points as
            a DataFrame), `arena_center`, `arena_radius`, `video_id`, and
            optionally `stimulus` (a `StimulusParams`).
        output_dir: Folder to write into. Created if needed.
        window_step_seconds: Time between window starts, in seconds, used for
            dwell times. It is not derived from the frame rate, so set it to
            match the window step used.

    Returns:
        A dictionary with the labeled `windows`, the chosen `gmm`, `bic_df`,
        `best_k`, the transition matrix `T`, the stationary distribution
        `pi`, `dwell_secs`, `dwell_runs` and the Markov `summary`.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Order parameters, feature matrix
    print("[pipeline] Step 1+2: computing order parameters and building feature matrix …")
    windows = _build_feature_matrix(videos)

    # GMM clustering
    print("[pipeline] Step 3: fitting GMM models …")
    windows, gmm, bic_df, best_k = _cluster(windows)

    # Markov model
    print("[pipeline] Step 4: building Markov model …")
    T, pi, dwell_secs, dwell_runs, summary = _markov(windows, best_k, window_step_seconds)

    sanity_lines = _sanity_checks(windows, best_k)
    report = _evaluation_report(windows, gmm, best_k, T, pi, dwell_secs, sanity_lines, window_step_seconds)
    windows.to_parquet(output_dir / "windows.parquet", index=False)

    joblib.dump(gmm, output_dir / "gmm_model.pkl")

    bic_df.to_csv(output_dir / "bic_scores.csv", index=False)

    state_labels = [f"state_{i}" for i in range(best_k)]
    pd.DataFrame(T, index=state_labels, columns=state_labels).to_csv(
        output_dir / "transition_matrix.csv"
    )

    with open(output_dir / "markov_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    if not dwell_runs.empty:
        dwell_runs.to_parquet(output_dir / "dwell_runs.parquet", index=False)
    else:
        pd.DataFrame(columns=["state", "length_windows", "length_seconds", "video_id"]).to_parquet(
            output_dir / "dwell_runs.parquet", index=False
        )

    with open(output_dir / "evaluation_report.txt", "w") as f:
        f.write(report)

    print(report)

    return {
        "windows": windows,
        "gmm": gmm,
        "bic_df": bic_df,
        "best_k": best_k,
        "T": T,
        "pi": pi,
        "dwell_secs": dwell_secs,
        "dwell_runs": dwell_runs,
        "summary": summary,
    }
