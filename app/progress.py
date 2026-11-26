"""In-memory progress reporting for running jobs.

Long jobs call `set_progress` from their worker thread, and the
`/processing-runs/{id}/progress` endpoint reads it with `get_progress`.

Progress lives only in the memory of the server process. It is lost on
restart and is not shared between processes, so it works only with a single
server process. The run's status in the database is the reliable record.
"""

from __future__ import annotations

from threading import Lock

_store: dict[str, dict] = {}
_lock = Lock()


def set_progress(run_id: str, done: int, total: int) -> None:
    """Record how far a run has got. Safe to call from any thread.

    Args:
        run_id: The processing run's ID, as a string.
        done: Units of work finished, usually frames.
        total: Total units of work.
    """
    with _lock:
        _store[run_id] = {"done": done, "total": total}


def get_progress(run_id: str) -> dict:
    """Return a run's progress.

    Args:
        run_id: The processing run's ID, as a string.

    Returns:
        A dictionary with `done` and `total`. Both are 0 if nothing has been
        recorded, which also happens after the run finishes.
    """
    with _lock:
        return dict(_store.get(run_id, {"done": 0, "total": 0}))


def clear_progress(run_id: str) -> None:
    """Forget a run's progress, usually once its computation has finished.

    Args:
        run_id: The processing run's ID, as a string.
    """
    with _lock:
        _store.pop(run_id, None)
