"""Background job for the final step, Collective Behavior.

`run_collective_behavior_experiment_job` analyzes every eligible video of
an experiment together, split into stimulus and no-stimulus conditions. It
computes windowed order parameters, fits a Gaussian mixture to find
states, and builds a Markov model of the transitions. See
[Collective behavior](../pipeline/collective-behavior.md).
"""

from __future__ import annotations

import io
import json
import logging
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from sqlalchemy import select

from app import storage
from app.crud.base import get_or_create
from app.database import AsyncSessionLocal
from app.models import (
    Dataset,
    DatasetFile,
    DatasetSpatialMetadata,
    DatasetType,
    DatasetVersion,
    File,
    FileVersion,
    MetricDefinition,
    MetricResult,
    ProcessingRun,
    ProcessingRunInput,
    ProcessingRunOutput,
    Tool,
    ToolVersion,
)

log = logging.getLogger(__name__)
from app.analysis.order_parameters import StimulusParams
from app.analysis.clustering import FEATURES, FEATURES_NO_STIMULUS, fit_gmm_models, select_best_k, assign_states
from app.analysis.markov import (
    build_transition_matrix,
    compute_dwell_runs,
    markov_summary,
    mean_dwell_times,
    stationary_distribution,
)
from app.tracking.io import read_trajectory_csv

TOOL_NAME = "Collective Behavior Analysis"
"""Tool name recorded on the run."""

TOOL_VERSION_LABEL = "1.0.0"
"""Tool version of the single-video analysis."""

DATASET_TYPE_KEY = "collective_behavior_windows"
"""Dataset type of the outputs."""

_METRIC_DEFS = {
    "collective_behavior_best_k":    ("Best GMM k",               None,  "scalar", "group"),
    "collective_behavior_mean_p":    ("Mean Polarization P",       None,  "scalar", "group"),
    "collective_behavior_mean_m":    ("Mean Milling M",            None,  "scalar", "group"),
    "collective_behavior_mean_s":    ("Mean Synchronization S",    None,  "scalar", "group"),
    "collective_behavior_n_windows": ("Clustered Window Count",    None,  "scalar", "group"),
}


def _to_parquet_bytes(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame as Parquet. Needs `pyarrow`."""
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    return buf.getvalue()


def _to_pkl_bytes(obj) -> bytes:
    """Serialize an object, such as a fitted model, with joblib."""
    buf = io.BytesIO()
    joblib.dump(obj, buf)
    return buf.getvalue()


def _apply_frame_step(df: pd.DataFrame, frame_step: int) -> pd.DataFrame:
    """Keep every `frame_step`-th frame and renumber frames 0, 1, 2, …

    Used to test how results change at a lower frame rate.
    """
    df = df[df["frame"] % frame_step == 0].copy()
    df["frame"] = df["frame"] // frame_step
    return df


def _run_analysis(
    trajectory_path,
    fps: float | None,
    arena_center: tuple[float, float],
    arena_radius: float,
    stimulus_params: dict | None,
    frame_step: int = 1,
    window_size: int | None = None,
    window_step: int | None = None,
) -> dict:
    """Run the analysis on one trajectory file. Runs in a worker thread.

    States are ordered by mean `S_normalized`. Without a stimulus, S is
    missing and filled with 0.5 for clustering. The window step in seconds,
    used for dwell times, is the window step divided by the frame rate, or
    the step in frames if there is no frame rate.

    With `frame_step` above 1, frames are thinned and the frame rate is
    divided accordingly, but the stimulus's `omega` (degrees per frame) is
    not rescaled. The experiment-level analysis does rescale it.

    Returns:
        The six output files as bytes, plus `best_k`, `mean_p`, `mean_m`,
        `mean_s` (0.0 if there is no S) and `n_windows_clustered`.

    Raises:
        ValueError: If no window passes the filters.
    """
    # CPU Usage Analysis
    from app.analysis.order_parameters import (
        compute_window_features,
        _DEFAULT_WINDOW_SIZE,
        _DEFAULT_WINDOW_STEP,
    )

    # Load tracks
    raw_tracks = read_trajectory_csv(trajectory_path.read_bytes())
    rows = [
        {"track_id": tid, "frame": p.frame, "x": p.x, "y": p.y, "is_predicted": p.is_predicted}
        for tid, pts in raw_tracks.items()
        for p in pts
    ]
    df = pd.DataFrame(rows)

    if frame_step > 1:
        df = _apply_frame_step(df, frame_step)
        if fps:
            fps = fps / frame_step

    stimulus = (
        StimulusParams(
            omega=float(stimulus_params["omega"]),
            theta_light_0=float(stimulus_params.get("theta_light_0", 0.0)),
        )
        if stimulus_params and stimulus_params.get("omega", 0) != 0
        else None
    )

    # Step 1+2: feature matrix
    feature_rows = compute_window_features(
        df=df,
        arena_center=arena_center,
        arena_radius=arena_radius,
        stimulus=stimulus,
        video_id="single",
        window_size=window_size or _DEFAULT_WINDOW_SIZE,
        window_step=window_step or _DEFAULT_WINDOW_STEP,
    )
    if not feature_rows:
        raise ValueError("No valid windows produced — check track data and arena parameters.")

    windows = pd.DataFrame(feature_rows)
    windows["S_normalized"] = (windows["S"] + 1.0) / 2.0
    windows["included_in_clustering"] = windows["N"] >= 5

    # Step 3: GMM
    models, bic_df = fit_gmm_models(windows)
    best_k = select_best_k(models, bic_df)
    best_gmm = models[best_k][0]
    windows = assign_states(windows, best_gmm)

    # Step 4: Markov
    _wstep_frames = window_step or _DEFAULT_WINDOW_STEP
    _wstep_secs = _wstep_frames / fps if fps else float(_wstep_frames)
    T = build_transition_matrix(windows, best_k)
    pi = stationary_distribution(T)
    dwell_secs = mean_dwell_times(T, _wstep_secs)
    dwell_runs = compute_dwell_runs(windows, _wstep_secs)
    summary = markov_summary(T, pi, dwell_secs, windows)

    state_labels = [f"state_{i}" for i in range(best_k)]
    T_df = pd.DataFrame(T, index=state_labels, columns=state_labels)

    return {
        "windows_bytes":           _to_parquet_bytes(windows),
        "gmm_bytes":               _to_pkl_bytes(best_gmm),
        "bic_bytes":               bic_df.to_csv(index=False).encode(),
        "transition_bytes":        T_df.to_csv().encode(),
        "summary_bytes":           json.dumps(summary, indent=2).encode(),
        "dwell_runs_bytes":        _to_parquet_bytes(dwell_runs) if not dwell_runs.empty
                                   else _to_parquet_bytes(
                                       pd.DataFrame(columns=["state","length_windows","length_seconds","video_id"])
                                   ),
        "best_k":                  best_k,
        "mean_p":                  float(windows["P"].mean()),
        "mean_m":                  float(windows["M"].mean()),
        "mean_s":                  float(windows["S"].dropna().mean()) if windows["S"].notna().any() else 0.0,
        "n_windows_clustered":     int(windows["included_in_clustering"].sum()),
    }


async def run_collective_behavior_job(
    processing_run_id: uuid.UUID,
    trajectory_file_version_id: uuid.UUID,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID,
    params: dict,
) -> None:
    """Analyze one trajectory file and store the results.

    Saves `windows.parquet`, `gmm_model.pkl`, `bic_scores.csv`,
    `transition_matrix.csv`, `markov_summary.json` and `dwell_runs.parquet`
    in a new `collective_behavior_windows` dataset, and records the metrics
    `collective_behavior_best_k`, `_mean_p`, `_mean_m`, `_mean_s` and
    `_n_windows`.

    The interface does not currently start this job; it uses the
    experiment-level job instead.

    Args:
        processing_run_id: The run, in status `queued`.
        trajectory_file_version_id: The trajectory CSV to analyze.
        experiment_id: The experiment the outputs belong to.
        user_id: The user who started the run.
        params: `arena_center_x`, `arena_center_y`, `arena_radius`, and
            optionally `stimulus` (`omega` in degrees per frame and
            `theta_light_0` in degrees), `fps`, `frame_step`, `window_size`
            and `window_step`.
    """
    import asyncio

    async with AsyncSessionLocal() as db:
        run = await db.get(ProcessingRun, processing_run_id)
        try:
            run.status = "running"
            run.started_at = datetime.now(timezone.utc)
            await db.commit()

            traj_version = await db.get(FileVersion, trajectory_file_version_id)
            spatial = await db.get(DatasetSpatialMetadata, traj_version.file_id)  # may be None

            # FPS: prefer params override, fall back to spatial metadata
            fps = params.get("fps") or (
                float(spatial.sampling_rate_hz) if spatial and spatial.sampling_rate_hz else None
            )

            arena_center = (float(params["arena_center_x"]), float(params["arena_center_y"]))
            arena_radius = float(params["arena_radius"])
            stimulus_params = params.get("stimulus")  # dict or None

            result = await asyncio.to_thread(
                _run_analysis,
                storage.full_path(traj_version.storage_key),
                fps,
                arena_center,
                arena_radius,
                stimulus_params,
                frame_step=int(params.get("frame_step") or 1),
                window_size=params.get("window_size"),
                window_step=params.get("window_step"),
            )

            prefix = f"experiments/{experiment_id}/processing-runs/{processing_run_id}"

            _EXT_TO_FILE_TYPE = {
                "csv": "csv", "json": "json", "pkl": "model",
                "parquet": "other", "txt": "log",
            }

            def _save(data: bytes, name: str, mime: str) -> tuple:
                key, chk, size = storage.save_bytes(data, prefix, name)
                ext = name.rsplit(".", 1)[-1]
                f = File(
                    experiment_id=experiment_id,
                    file_type=_EXT_TO_FILE_TYPE.get(ext, "other"),
                    logical_name=name,
                    is_raw=False,
                    created_by=user_id,
                )
                return f, key, chk, size, mime

            output_specs = [
                ("windows.parquet",         result["windows_bytes"],         "application/octet-stream"),
                ("gmm_model.pkl",           result["gmm_bytes"],             "application/octet-stream"),
                ("bic_scores.csv",          result["bic_bytes"],             "text/csv"),
                ("transition_matrix.csv",   result["transition_bytes"],      "text/csv"),
                ("markov_summary.json",     result["summary_bytes"],         "application/json"),
                ("dwell_runs.parquet",      result["dwell_runs_bytes"],      "application/octet-stream"),
            ]

            file_version_ids: dict[str, uuid.UUID] = {}
            for logical_name, data, mime in output_specs:
                out_file, key, chk, size, mime = _save(data, logical_name, mime)
                db.add(out_file)
                await db.flush()
                out_ver = FileVersion(
                    file_id=out_file.id,
                    version_number=1,
                    storage_bucket=storage.STORAGE_BUCKET,
                    storage_key=key,
                    mime_type=mime,
                    size_bytes=size,
                    checksum_sha256=chk,
                    uploaded_by=user_id,
                    is_current=True,
                )
                db.add(out_ver)
                await db.flush()
                out_file.current_version_id = out_ver.id
                file_version_ids[logical_name] = out_ver.id

            # Dataset
            await get_or_create(db, DatasetType, key=DATASET_TYPE_KEY,
                                defaults={"display_name": "Collective Behavior Windows"})
            dataset = Dataset(
                experiment_id=experiment_id,
                dataset_type=DATASET_TYPE_KEY,
                name=f"Collective behavior - run {processing_run_id}",
                origin="automatic",
                status="valid",
                created_by=user_id,
            )
            db.add(dataset)
            await db.flush()
            dv = DatasetVersion(
                dataset_id=dataset.id,
                version_number=1,
                schema_version="collective-behavior-1.0",
                changelog="Order parameters, GMM states, and Markov transitions from positional tracks",
                created_by=user_id,
                is_current=True,
            )
            db.add(dv)
            await db.flush()
            dataset.current_version_id = dv.id

            # Role names mirror the file logical names (without extension)
            role_map = {
                "windows.parquet":        "windows",
                "gmm_model.pkl":          "gmm_model",
                "bic_scores.csv":         "bic_scores",
                "transition_matrix.csv":  "transition_matrix",
                "markov_summary.json":    "markov_summary",
                "dwell_runs.parquet":     "dwell_runs",
            }
            for logical_name, role in role_map.items():
                db.add(DatasetFile(
                    dataset_version_id=dv.id,
                    file_version_id=file_version_ids[logical_name],
                    role=role,
                ))

            db.add(ProcessingRunInput(
                processing_run_id=run.id,
                artifact_type="file_version",
                file_version_id=trajectory_file_version_id,
                role="trajectory",
            ))
            db.add(ProcessingRunOutput(
                processing_run_id=run.id,
                artifact_type="dataset_version",
                dataset_version_id=dv.id,
                role="primary_output",
            ))

            # Aggregate metrics
            for key, (display_name, unit, value_type, scope) in _METRIC_DEFS.items():
                await get_or_create(
                    db, MetricDefinition, key=key,
                    defaults={"display_name": display_name, "unit": unit,
                              "value_type": value_type, "scope": scope},
                )
            metric_values = {
                "collective_behavior_best_k":    float(result["best_k"]),
                "collective_behavior_mean_p":    result["mean_p"],
                "collective_behavior_mean_m":    result["mean_m"],
                "collective_behavior_mean_s":    result["mean_s"],
                "collective_behavior_n_windows": float(result["n_windows_clustered"]),
            }
            for metric_key, value in metric_values.items():
                db.add(MetricResult(
                    dataset_version_id=dv.id,
                    processing_run_id=run.id,
                    metric_key=metric_key,
                    value_numeric=value,
                ))

            run.status = "succeeded"
            run.completed_at = datetime.now(timezone.utc)
            run.runtime_info = {
                "best_k": result["best_k"],
                "n_windows_clustered": result["n_windows_clustered"],
                "mean_p": result["mean_p"],
                "mean_m": result["mean_m"],
                "mean_s": result["mean_s"],
            }
            await db.commit()

        except Exception as exc:
            await db.rollback()
            run = await db.get(ProcessingRun, processing_run_id)
            run.status = "failed"
            run.error_message = str(exc)[:2000]
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()


# Experiment-level collective behavior analysis

TOOL_VERSION_LABEL_EXPERIMENT = "2.0.0"
"""Tool version of the experiment-level analysis."""


def _find_startup_threshold(light_csv_path: Path) -> int | None:
    """Return the first frame where the light is visible, or None if it never is.

    Windows before this frame are skipped for stimulus videos, so the time
    before the light switches on is not analyzed as stimulus behavior.
    """
    df = pd.read_csv(light_csv_path)
    valid = df[(df["x"] > -1) & (df["y"] > -1)]
    if valid.empty:
        return None
    return int(valid["frame"].min())


def _theta_light_0_from_csv(light_csv_path: Path, omega_deg_per_frame: float) -> float:
    """Work out the light's angle at frame 0 from its first visible position.

    The angle at the first visible frame is wound back to frame 0 at the
    given constant speed. Used for imported light trajectories.

    Returns:
        The angle at frame 0 in degrees, or 0.0 if the light is never visible.
    """
    df = pd.read_csv(light_csv_path)
    valid = df[(df["x"] > -1) & (df["y"] > -1)]
    if valid.empty:
        return 0.0
    first = valid.iloc[0]
    theta_at_first = math.degrees(float(first["theta_rad"]))
    return theta_at_first - omega_deg_per_frame * int(first["frame"])


def _analyze_condition(
    windows: pd.DataFrame,
    features: list[str],
    sort_by: str,
    window_step_seconds: float = 1.0,
) -> dict:
    """Cluster and model the pooled windows of one condition.

    Besides the standard Markov summary, `markov_summary.json` gets the
    transition matrix and each state's mean P, M and, with a stimulus, S.

    Args:
        windows: Windows from all videos of the condition.
        features: Feature columns to cluster on.
        sort_by: Column used to order the states.
        window_step_seconds: Time between window starts, for dwell times.

    Returns:
        The six output files as bytes, plus `best_k`, `mean_p`, `mean_m`,
        `mean_s` (None without a stimulus) and `n_windows`.
    """
    models, bic_df = fit_gmm_models(windows, features=features)
    best_k = select_best_k(models, bic_df)
    best_gmm = models[best_k][0]
    windows = assign_states(windows, best_gmm, features=features, sort_by=sort_by)

    T = build_transition_matrix(windows, best_k)
    pi = stationary_distribution(T)
    dwell_secs = mean_dwell_times(T, window_step_seconds)
    dwell_runs = compute_dwell_runs(windows, window_step_seconds)
    summary = markov_summary(T, pi, dwell_secs, windows)

    # Enrich summary with transition matrix and per-state means
    state_labels = [f"state_{i}" for i in range(best_k)]
    summary["transition_matrix"] = {
        state_labels[i]: {state_labels[j]: float(T[i, j]) for j in range(best_k)}
        for i in range(best_k)
    }
    summary["state_means"] = {}
    for i in range(best_k):
        mask = windows["state"] == i
        entry: dict = {
            "mean_P": float(windows.loc[mask, "P"].mean()),
            "mean_M": float(windows.loc[mask, "M"].mean()),
        }
        if "S_normalized" in features and windows["S"].notna().any():
            entry["mean_S"] = float(windows.loc[mask, "S"].dropna().mean())
        summary["state_means"][state_labels[i]] = entry

    T_df = pd.DataFrame(T, index=state_labels, columns=state_labels)
    empty_dwell_cols = ["state", "length_windows", "length_seconds", "video_id"]

    return {
        "windows_bytes":     _to_parquet_bytes(windows),
        "gmm_bytes":         _to_pkl_bytes(best_gmm),
        "bic_bytes":         bic_df.to_csv(index=False).encode(),
        "transition_bytes":  T_df.to_csv().encode(),
        "summary_bytes":     json.dumps(summary, indent=2).encode(),
        "dwell_runs_bytes":  (
            _to_parquet_bytes(dwell_runs) if not dwell_runs.empty
            else _to_parquet_bytes(pd.DataFrame(columns=empty_dwell_cols))
        ),
        "best_k":            best_k,
        "mean_p":            float(windows["P"].mean()),
        "mean_m":            float(windows["M"].mean()),
        "mean_s":            float(windows["S"].dropna().mean()) if windows["S"].notna().any() else None,
        "n_windows":         int(windows["included_in_clustering"].sum()),
    }


def _run_experiment_analysis(
    video_data: list[dict],
    frame_step: int = 1,
    window_size: int | None = None,
    window_step: int | None = None,
) -> dict:
    """Compute windows for every video and analyze each condition. Runs in a worker thread.

    For stimulus videos, windows before the light first appears are skipped,
    and a stimulus video whose light never appears is left out. Windows are
    pooled per condition, and each condition gets its own mixture model and
    Markov model. In both conditions states are ordered by mean P. The
    no-stimulus condition clusters on P, P_local and M only.

    With `frame_step` above 1, frames are thinned, and the frame rate,
    `omega` and the startup frame are rescaled to match.

    The window step in seconds comes from the first video with a frame rate
    and is used for every video, so videos are assumed to share one rate.

    Args:
        video_data: One dictionary per video, as assembled by
            `run_collective_behavior_experiment_job`.
        frame_step: Keep one frame in every `frame_step`.
        window_size: Window length in frames, or None for the default.
        window_step: Distance between window starts in frames, or None for
            the default.

    Returns:
        Results keyed by condition (`stimulus`, `no_stimulus`), each as
        returned by `_analyze_condition`. A condition with no valid windows
        is left out, with a warning in the server log.

    Raises:
        ValueError: If neither condition has any valid windows.
    """
    # CPU Compute Windows, split by stimulus
    from app.analysis.order_parameters import (
        compute_window_features,
        _DEFAULT_WINDOW_SIZE,
        _DEFAULT_WINDOW_STEP,
    )

    ws = window_size or _DEFAULT_WINDOW_SIZE
    wstep = window_step or _DEFAULT_WINDOW_STEP
    _first_fps = next(
        (vd["fps"] / frame_step if frame_step > 1 else vd["fps"]
         for vd in video_data if vd.get("fps")),
        None,
    )
    _wstep_secs = wstep / _first_fps if _first_fps else float(wstep)

    stimulus_windows: list[pd.DataFrame] = []
    no_stimulus_windows: list[pd.DataFrame] = []

    for vd in video_data:
        raw_tracks = read_trajectory_csv(Path(vd["positional_path"]).read_bytes())
        rows = [
            {"track_id": tid, "frame": p.frame, "x": p.x, "y": p.y, "is_predicted": p.is_predicted}
            for tid, pts in raw_tracks.items()
            for p in pts
        ]
        df = pd.DataFrame(rows)

        if frame_step > 1:
            df = _apply_frame_step(df, frame_step)
            vd = {**vd}
            if vd.get("fps"):
                vd["fps"] = vd["fps"] / frame_step
            if vd.get("stimulus"):
                vd["stimulus"] = {**vd["stimulus"], "omega": float(vd["stimulus"]["omega"]) * frame_step}

        startup_threshold: int | None = None
        if vd["condition"] == "stimulus":
            light_path = vd.get("light_csv_path")
            if light_path:
                startup_threshold = _find_startup_threshold(Path(light_path))
            if startup_threshold is None:
                log.warning(
                    "Video %s: declared stimulus but LED never becomes active — skipping",
                    vd["video_id"],
                )
                continue
            # Light frame number → detection sample index (first sample at or after it)
            k = float(vd.get("light_frames_per_sample") or 1.0)
            f0 = float(vd.get("light_frame_at_sample0") or 0.0)
            startup_threshold = max(0, math.ceil((startup_threshold - f0) / k - 1e-9))
            if frame_step > 1:
                startup_threshold = -(-startup_threshold // frame_step)

        stim_cfg = vd.get("stimulus")
        stimulus = (
            StimulusParams(
                omega=float(stim_cfg["omega"]),
                theta_light_0=float(stim_cfg.get("theta_light_0", 0.0)),
            )
            if stim_cfg and stim_cfg.get("omega", 0) != 0
            else None
        )

        feature_rows = compute_window_features(
            df=df,
            arena_center=vd["arena_center"],
            arena_radius=vd["arena_radius"],
            stimulus=stimulus,
            video_id=vd["video_id"],
            startup_threshold=startup_threshold,
            window_size=ws,
            window_step=wstep,
        )
        if not feature_rows:
            log.warning("Video %s: no valid windows after filtering — skipping", vd["video_id"])
            continue

        win_df = pd.DataFrame(feature_rows)
        win_df["S_normalized"] = (win_df["S"] + 1.0) / 2.0
        win_df["included_in_clustering"] = win_df["N"] >= 5

        if vd["condition"] == "stimulus":
            stimulus_windows.append(win_df)
        else:
            no_stimulus_windows.append(win_df)

    results: dict[str, dict] = {}

    if stimulus_windows:
        stim_df = pd.concat(stimulus_windows, ignore_index=True)
        results["stimulus"] = _analyze_condition(stim_df, features=FEATURES, sort_by="P", window_step_seconds=_wstep_secs)
    else:
        log.warning("No valid stimulus windows found across all videos.")

    if no_stimulus_windows:
        nostim_df = pd.concat(no_stimulus_windows, ignore_index=True)
        results["no_stimulus"] = _analyze_condition(
            nostim_df, features=FEATURES_NO_STIMULUS, sort_by="P", window_step_seconds=_wstep_secs
        )
    else:
        log.warning("No valid no-stimulus windows found across all videos.")

    if not results:
        raise ValueError("No valid windows found in any video after filtering.")

    n_stim = len(stimulus_windows)
    n_nostim = len(no_stimulus_windows)
    if n_stim < 2 and "stimulus" in results:
        log.warning("Only %d stimulus video(s) — Markov estimates may not be reliable.", n_stim)
    if n_nostim < 2 and "no_stimulus" in results:
        log.warning(
            "Only %d no-stimulus video(s) — Markov estimates may not be reliable.", n_nostim
        )

    return results


async def _get_latest_run_for_video(
    db,
    experiment_id: uuid.UUID,
    tool_name: str,
    video_fv_id: str,
) -> ProcessingRun | None:
    """Find the newest succeeded run of a tool for a video.

    Runs are matched on `parameters["source_file_version_id"]`.

    Returns:
        The run, or None if there is none.
    """
    stmt = (
        select(ProcessingRun)
        .join(ToolVersion, ProcessingRun.tool_version_id == ToolVersion.id)
        .join(Tool, ToolVersion.tool_id == Tool.id)
        .where(
            ProcessingRun.experiment_id == experiment_id,
            ProcessingRun.status == "succeeded",
            Tool.name == tool_name,
            ProcessingRun.parameters["source_file_version_id"].astext == video_fv_id,
        )
        .order_by(ProcessingRun.created_at.desc())
        .limit(1)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    return row


async def _get_primary_output_fv(db, run_id: uuid.UUID) -> FileVersion | None:
    """Return the file version a run produced as its primary output.

    This is the version linked to the run's output dataset, which is the
    version the run itself wrote. Later versions of the same file, such as
    trajectories corrected in the editor, are not returned.

    Returns:
        The file version, or None if the run has no output dataset or the
        dataset has no primary file.
    """
    # Follow ProcessingRunOutput → DatasetVersion → DatasetFile(primary) → FileVersion.
    stmt_out = select(ProcessingRunOutput).where(
        ProcessingRunOutput.processing_run_id == run_id,
        ProcessingRunOutput.artifact_type == "dataset_version",
    )
    out_rec = (await db.execute(stmt_out)).scalar_one_or_none()
    if not out_rec:
        return None
    stmt_df = select(DatasetFile).where(
        DatasetFile.dataset_version_id == out_rec.dataset_version_id,
        DatasetFile.role == "primary",
    )
    df_rec = (await db.execute(stmt_df)).scalar_one_or_none()
    if not df_rec:
        return None
    return await db.get(FileVersion, df_rec.file_version_id)


async def _get_detection_sampling(db, experiment_id: uuid.UUID, tracking_run: ProcessingRun) -> dict:
    """Return how the detections behind a tracking run were sampled.

    Detection numbers the frames it processes 0, 1, 2, … (sample indices).
    Sample `s` is video frame `start_frame + s × frame_step`. The light
    trajectory counts frames at its own rate, so the analysis needs these
    values to line the two up in time.

    Returns:
        `frame_step`, `start_frame` and `fps` (the detection's effective frame
        rate, or None). Tracks with no matching detection run, such as imported
        positions, are treated as one sample per video frame.
    """
    det_fv_id = (tracking_run.parameters or {}).get("detections_file_version_id")
    if det_fv_id:
        stmt = (
            select(ProcessingRun)
            .join(ToolVersion, ProcessingRun.tool_version_id == ToolVersion.id)
            .join(Tool, ToolVersion.tool_id == Tool.id)
            .where(
                ProcessingRun.experiment_id == experiment_id,
                ProcessingRun.status == "succeeded",
                Tool.name == "Subject Detector",
                ProcessingRun.runtime_info["detections_file_version_id"].astext == str(det_fv_id),
            )
            .limit(1)
        )
        det_run = (await db.execute(stmt)).scalar_one_or_none()
        if det_run:
            p = det_run.parameters or {}
            return {
                "frame_step": max(1, int(p.get("frame_step") or 1)),
                "start_frame": max(0, int(p.get("start_frame") or 0)),
                "fps": (det_run.runtime_info or {}).get("fps"),
            }
    return {"frame_step": 1, "start_frame": 0, "fps": None}


_EXPERIMENT_METRIC_DEFS = {
    "cb_experiment_best_k_{cond}":     ("Best GMM k ({cond})",              None,  "scalar", "group"),
    "cb_experiment_mean_p_{cond}":     ("Mean Polarization P ({cond})",     None,  "scalar", "group"),
    "cb_experiment_mean_m_{cond}":     ("Mean Milling M ({cond})",          None,  "scalar", "group"),
    "cb_experiment_mean_s_{cond}":     ("Mean Synchronization S ({cond})",  None,  "scalar", "group"),
    "cb_experiment_n_windows_{cond}":  ("Clustered Window Count ({cond})",  None,  "scalar", "group"),
}


async def run_collective_behavior_experiment_job(
    processing_run_id: uuid.UUID,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID,
    params: dict,
) -> None:
    """Analyze all eligible videos of an experiment, by condition.

    A video is eligible if it has a succeeded light-tracking run and a
    succeeded positional-tracking run, and the tracking output can be found.
    For each one, the newest light-tracking run supplies:

    - the arena center and radius;
    - the frame rate, unless `params["fps"]` overrides it;
    - the condition and the stimulus's motion. For a calibrated light, omega
      is 360 / `frames_per_rotation` degrees per frame, signed by
      `direction`. For an imported light, the video counts as stimulus if
      its mean angular velocity exceeds 0.01 rad/s.

    Each condition's results are saved as six files with the condition as a
    suffix (for example `windows_stimulus.parquet`), in a dataset of their
    own, linked to the run as `primary_output_<condition>`. Metrics are
    named `cb_experiment_<metric>_<condition>`.

    Args:
        processing_run_id: The run, in status `queued`.
        experiment_id: The experiment to analyze.
        user_id: The user who started the run.
        params: Optional `fps`, `frame_step`, `window_size` and `window_step`.
    """
    import asyncio

    async with AsyncSessionLocal() as db:
        run = await db.get(ProcessingRun, processing_run_id)
        try:
            run.status = "running"
            run.started_at = datetime.now(timezone.utc)
            await db.commit()

            # Discover all videos for this experiment
            stmt_videos = select(File).where(
                File.experiment_id == experiment_id,
                File.file_type == "video",
                File.deleted_at.is_(None),
            )
            video_files = (await db.execute(stmt_videos)).scalars().all()

            fps_override = params.get("fps")
            video_data: list[dict] = []

            for vf in video_files:
                if not vf.current_version_id:
                    continue
                vid_str = str(vf.current_version_id)

                light_run = await _get_latest_run_for_video(
                    db, experiment_id, "Manual Circular Trajectory", vid_str
                )
                if not light_run:
                    log.info("Video %s: no succeeded light tracking run — skipping", vid_str)
                    continue

                tracking_run = await _get_latest_run_for_video(
                    db, experiment_id, "Positional Tracker", vid_str
                )
                if not tracking_run:
                    log.info("Video %s: no succeeded positional tracking run — skipping", vid_str)
                    continue

                tracking_fv = await _get_primary_output_fv(db, tracking_run.id)
                if not tracking_fv:
                    log.warning("Video %s: cannot resolve tracking output file — skipping", vid_str)
                    continue

                # Use the file's current version, so trajectories confirmed in the editor are analyzed
                tracking_file = await db.get(File, tracking_fv.file_id)
                if tracking_file and tracking_file.current_version_id:
                    current_fv = await db.get(FileVersion, tracking_file.current_version_id)
                    if current_fv:
                        tracking_fv = current_fv

                light_fv = await _get_primary_output_fv(db, light_run.id)

                lp = light_run.parameters
                is_csv_import = bool(lp.get("csv_import"))

                arena_center = (float(lp["center_x"]), float(lp["center_y"]))
                arena_radius = float(lp["radius_px"])

                # The light trajectory counts frames at its own rate (the video's rate for a
                # calibration, the import rate for a light CSV). The tracks count detection
                # samples. Line them up in time: sample s is at (start + s × step) / native fps,
                # light frame f is at f / light fps.
                sampling = await _get_detection_sampling(db, experiment_id, tracking_run)
                light_fps = (
                    float(light_run.runtime_info["source_fps"])
                    if light_run.runtime_info and "source_fps" in light_run.runtime_info
                    else None
                )
                sample_fps = sampling["fps"]
                if light_fps and sample_fps:
                    native_fps = sample_fps * sampling["frame_step"]
                    light_frames_per_sample = light_fps / sample_fps
                    light_frame_at_sample0 = light_fps * sampling["start_frame"] / native_fps
                else:
                    # No detection run (e.g. imported positions): assume the same frame numbering
                    light_frames_per_sample, light_frame_at_sample0 = 1.0, 0.0

                fps = fps_override or sample_fps or light_fps

                if is_csv_import:
                    ri = light_run.runtime_info or {}
                    omega_rad_s = float(ri.get("angular_velocity_rad_s", 0.0))
                    is_stimulus = abs(omega_rad_s) > 0.01
                    if is_stimulus and light_fps:
                        omega_deg_per_frame = math.degrees(omega_rad_s / light_fps)
                        light_csv_path_str = str(storage.full_path(light_fv.storage_key)) if light_fv else None
                        if light_csv_path_str:
                            theta_light_0 = _theta_light_0_from_csv(
                                Path(light_csv_path_str), omega_deg_per_frame
                            )
                        else:
                            theta_light_0 = 0.0
                        stimulus_cfg = {"omega": omega_deg_per_frame, "theta_light_0": theta_light_0}
                    else:
                        stimulus_cfg = None
                elif lp.get("first_frame") is not None:
                    is_stimulus = True
                    omega = (360.0 / float(lp["frames_per_rotation"])) * int(lp["direction"])
                    theta_at_first = math.degrees(math.atan2(
                        float(lp["first_y"]) - arena_center[1],
                        float(lp["first_x"]) - arena_center[0],
                    ))
                    theta_light_0 = theta_at_first - omega * float(lp["first_frame"])
                    stimulus_cfg = {"omega": omega, "theta_light_0": theta_light_0}
                else:
                    is_stimulus = False
                    stimulus_cfg = None

                # Above, omega is per light frame and theta_light_0 is at light frame 0.
                # Restate both per detection sample: angle = theta0 + omega × (f0 + k × s).
                if stimulus_cfg:
                    stimulus_cfg = {
                        "omega": stimulus_cfg["omega"] * light_frames_per_sample,
                        "theta_light_0": stimulus_cfg["theta_light_0"]
                        + stimulus_cfg["omega"] * light_frame_at_sample0,
                    }

                video_data.append({
                    "light_frames_per_sample": light_frames_per_sample,
                    "light_frame_at_sample0":  light_frame_at_sample0,
                    "video_id":       vid_str,
                    "condition":      "stimulus" if is_stimulus else "no_stimulus",
                    "positional_path": str(storage.full_path(tracking_fv.storage_key)),
                    "light_csv_path": str(storage.full_path(light_fv.storage_key)) if light_fv else None,
                    "arena_center":   arena_center,
                    "arena_radius":   arena_radius,
                    "stimulus":       stimulus_cfg,
                    "fps":            fps,
                })

            if not video_data:
                raise ValueError(
                    "No videos with both a succeeded light tracking run and positional "
                    "tracking run were found in this experiment."
                )

            condition_results: dict[str, dict] = await asyncio.to_thread(
                _run_experiment_analysis,
                video_data,
                frame_step=int(params.get("frame_step") or 1),
                window_size=params.get("window_size"),
                window_step=params.get("window_step"),
            )

            # 2. Save outputs and register each condition's dataset
            prefix = f"experiments/{experiment_id}/processing-runs/{processing_run_id}"
            _EXT_TO_FILE_TYPE = {
                "csv": "csv", "json": "json", "pkl": "model",
                "parquet": "other",
            }

            def _save(data: bytes, name: str, mime: str):
                key, chk, size = storage.save_bytes(data, prefix, name)
                ext = name.rsplit(".", 1)[-1]
                f = File(
                    experiment_id=experiment_id,
                    file_type=_EXT_TO_FILE_TYPE.get(ext, "other"),
                    logical_name=name,
                    is_raw=False,
                    created_by=user_id,
                )
                return f, key, chk, size, mime

            tool = await get_or_create(
                db, Tool, name=TOOL_NAME,
                defaults={
                    "category": "analysis",
                    "description": "Condition-split GMM + Markov collective behavior analysis",
                },
            )
            await get_or_create(
                db, ToolVersion, tool_id=tool.id, version_label=TOOL_VERSION_LABEL_EXPERIMENT
            )
            await get_or_create(
                db, DatasetType, key=DATASET_TYPE_KEY,
                defaults={"display_name": "Collective Behavior Windows"},
            )

            runtime_summary: dict = {}

            for cond, res in condition_results.items():
                suffix = f"_{cond}"
                output_specs = [
                    (f"windows{suffix}.parquet",        res["windows_bytes"],    "application/octet-stream"),
                    (f"gmm_model{suffix}.pkl",           res["gmm_bytes"],        "application/octet-stream"),
                    (f"bic_scores{suffix}.csv",          res["bic_bytes"],        "text/csv"),
                    (f"transition_matrix{suffix}.csv",   res["transition_bytes"], "text/csv"),
                    (f"markov_summary{suffix}.json",     res["summary_bytes"],    "application/json"),
                    (f"dwell_runs{suffix}.parquet",      res["dwell_runs_bytes"], "application/octet-stream"),
                ]

                fv_ids: dict[str, uuid.UUID] = {}
                for logical_name, data, mime in output_specs:
                    out_file, key, chk, size, mime_ = _save(data, logical_name, mime)
                    db.add(out_file)
                    await db.flush()
                    out_ver = FileVersion(
                        file_id=out_file.id,
                        version_number=1,
                        storage_bucket=storage.STORAGE_BUCKET,
                        storage_key=key,
                        mime_type=mime_,
                        size_bytes=size,
                        checksum_sha256=chk,
                        uploaded_by=user_id,
                        is_current=True,
                    )
                    db.add(out_ver)
                    await db.flush()
                    out_file.current_version_id = out_ver.id
                    fv_ids[logical_name] = out_ver.id

                dataset = Dataset(
                    experiment_id=experiment_id,
                    dataset_type=DATASET_TYPE_KEY,
                    name=f"Collective behavior ({cond}) - run {processing_run_id}",
                    origin="automatic",
                    status="valid",
                    created_by=user_id,
                )
                db.add(dataset)
                await db.flush()
                dv = DatasetVersion(
                    dataset_id=dataset.id,
                    version_number=1,
                    schema_version="collective-behavior-2.0",
                    changelog=f"Condition-split GMM + Markov ({cond})",
                    created_by=user_id,
                    is_current=True,
                )
                db.add(dv)
                await db.flush()
                dataset.current_version_id = dv.id

                role_map = {
                    f"windows{suffix}.parquet":       "windows",
                    f"gmm_model{suffix}.pkl":          "gmm_model",
                    f"bic_scores{suffix}.csv":         "bic_scores",
                    f"transition_matrix{suffix}.csv":  "transition_matrix",
                    f"markov_summary{suffix}.json":    "markov_summary",
                    f"dwell_runs{suffix}.parquet":     "dwell_runs",
                }
                for logical_name, role in role_map.items():
                    db.add(DatasetFile(
                        dataset_version_id=dv.id,
                        file_version_id=fv_ids[logical_name],
                        role=role,
                    ))

                db.add(ProcessingRunOutput(
                    processing_run_id=run.id,
                    artifact_type="dataset_version",
                    dataset_version_id=dv.id,
                    role=f"primary_output_{cond}",
                ))

                # Per-condition scalar metrics (naming: cb_experiment_<metric>_<cond>)
                metric_values = {
                    f"cb_experiment_best_k_{cond}":    float(res["best_k"]),
                    f"cb_experiment_mean_p_{cond}":    res["mean_p"],
                    f"cb_experiment_mean_m_{cond}":    res["mean_m"],
                    f"cb_experiment_n_windows_{cond}": float(res["n_windows"]),
                }
                if res["mean_s"] is not None:
                    metric_values[f"cb_experiment_mean_s_{cond}"] = res["mean_s"]

                for mk, mv in metric_values.items():
                    cond_label = cond.replace("_", " ").title()
                    base_key = mk.replace(f"_{cond}", "").replace("cb_experiment_", "")
                    display = f"{base_key.replace('_', ' ').title()} ({cond_label})"
                    await get_or_create(
                        db, MetricDefinition, key=mk,
                        defaults={"display_name": display, "unit": None,
                                  "value_type": "scalar", "scope": "group"},
                    )
                    db.add(MetricResult(
                        dataset_version_id=dv.id,
                        processing_run_id=run.id,
                        metric_key=mk,
                        value_numeric=mv,
                    ))

                runtime_summary[cond] = {
                    "best_k": res["best_k"],
                    "n_windows": res["n_windows"],
                    "mean_p": res["mean_p"],
                    "mean_m": res["mean_m"],
                    "mean_s": res["mean_s"],
                }

            run.status = "succeeded"
            run.completed_at = datetime.now(timezone.utc)
            run.runtime_info = {
                "n_videos_processed": len(video_data),
                "conditions": runtime_summary,
            }
            await db.commit()

        except Exception as exc:
            await db.rollback()
            run = await db.get(ProcessingRun, processing_run_id)
            run.status = "failed"
            run.error_message = str(exc)[:2000]
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
