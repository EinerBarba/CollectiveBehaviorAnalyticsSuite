from __future__ import annotations

import asyncio
import io
import json
import math
import uuid

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import storage
from app.database import get_db
from app.deps import get_current_user
from app.models import DatasetFile, FileVersion, ProcessingRun, ProcessingRunOutput, User

router = APIRouter(tags=["cb-results"])


def _sanitize(obj):
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


_WINDOW_COLS = [
    "video_id", "window_index", "N", "valid_fraction",
    "P", "P_local", "M", "S", "state", "assignment_entropy",
]


def _read_windows(data: bytes) -> list[dict]:
    df = pd.read_parquet(io.BytesIO(data))
    cols = [c for c in _WINDOW_COLS if c in df.columns]
    df = df[cols]
    return df.where(df.notna(), other=None).to_dict(orient="records")


def _read_transition(data: bytes) -> list[list[float]]:
    df = pd.read_csv(io.BytesIO(data), index_col=0)
    return df.values.tolist()


async def _build_condition_payload(db, out_row: ProcessingRunOutput, runtime_cond: dict) -> dict:
    file_rows = (
        await db.execute(
            select(DatasetFile).where(
                DatasetFile.dataset_version_id == out_row.dataset_version_id
            )
        )
    ).scalars().all()
    role_to_fvid: dict[str, uuid.UUID] = {r.role: r.file_version_id for r in file_rows}

    async def _fetch(role: str) -> bytes:
        fvid = role_to_fvid.get(role)
        if fvid is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Output file '{role}' not found")
        fv = await db.get(FileVersion, fvid)
        if fv is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"FileVersion for '{role}' not found")
        path = storage.full_path(fv.storage_key)
        return await asyncio.to_thread(path.read_bytes)

    windows_bytes, markov_bytes, transition_bytes = await asyncio.gather(
        _fetch("windows"),
        _fetch("markov_summary"),
        _fetch("transition_matrix"),
    )

    windows, transition_matrix = await asyncio.gather(
        asyncio.to_thread(_read_windows, windows_bytes),
        asyncio.to_thread(_read_transition, transition_bytes),
    )

    markov = _sanitize(json.loads(markov_bytes.decode()))
    best_k = runtime_cond.get("best_k") or len(transition_matrix)

    return {
        "best_k": best_k,
        "has_stimulus": bool(runtime_cond.get("mean_s") is not None),
        "windows": _sanitize(windows),
        "transition_matrix": _sanitize(transition_matrix),
        "markov": markov,
    }


@router.get("/processing-runs/{run_id}/cb-results")
async def get_cb_results(
    run_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await db.get(ProcessingRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    if run.status != "succeeded":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Run is {run.status}, not succeeded")

    output_rows = (
        await db.execute(
            select(ProcessingRunOutput).where(
                ProcessingRunOutput.processing_run_id == run_id,
                ProcessingRunOutput.artifact_type == "dataset_version",
            )
        )
    ).scalars().all()

    if not output_rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No output dataset for this run")

    runtime_info = run.runtime_info or {}

    # Experiment-level run: roles are "primary_output_<condition>"
    multi_cond = [r for r in output_rows if r.role.startswith("primary_output_") and r.role != "primary_output"]
    if multi_cond:
        runtime_conds: dict = runtime_info.get("conditions", {})
        conditions: dict = {}
        for out_row in multi_cond:
            cond_name = out_row.role[len("primary_output_"):]
            payload = await _build_condition_payload(db, out_row, runtime_conds.get(cond_name, {}))
            payload["has_stimulus"] = cond_name == "stimulus"
            conditions[cond_name] = payload
        return {
            "run_id": str(run_id),
            "runtime_info": runtime_info,
            "conditions": conditions,
        }

    # Single-video run
    out_row = output_rows[0]
    file_rows = (
        await db.execute(
            select(DatasetFile).where(
                DatasetFile.dataset_version_id == out_row.dataset_version_id
            )
        )
    ).scalars().all()
    role_to_fvid: dict[str, uuid.UUID] = {r.role: r.file_version_id for r in file_rows}

    async def _fetch(role: str) -> bytes:
        fvid = role_to_fvid.get(role)
        if fvid is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Output file '{role}' not found")
        fv = await db.get(FileVersion, fvid)
        if fv is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"FileVersion for '{role}' not found")
        path = storage.full_path(fv.storage_key)
        return await asyncio.to_thread(path.read_bytes)

    windows_bytes, markov_bytes, transition_bytes = await asyncio.gather(
        _fetch("windows"),
        _fetch("markov_summary"),
        _fetch("transition_matrix"),
    )
    windows, transition_matrix = await asyncio.gather(
        asyncio.to_thread(_read_windows, windows_bytes),
        asyncio.to_thread(_read_transition, transition_bytes),
    )
    markov = _sanitize(json.loads(markov_bytes.decode()))
    params = run.parameters or {}
    has_stimulus = bool(params.get("stimulus") and params["stimulus"].get("omega", 0) != 0)

    return {
        "run_id": str(run_id),
        "best_k": runtime_info.get("best_k"),
        "has_stimulus": has_stimulus,
        "runtime_info": runtime_info,
        "windows": _sanitize(windows),
        "transition_matrix": _sanitize(transition_matrix),
        "markov": markov,
    }
