"""Background job registry for WordTape (spec task B4).

Dead-simple pattern: one active job at a time, work runs in a daemon
thread, the UI polls :func:`get_job`. The worker function receives the
:class:`Job` object and mutates ``done`` / ``total`` / ``message``
directly; :func:`cancel_job` only sets the ``cancelled`` flag — the
worker must poll ``job.cancelled`` itself and stop early.

Stdlib only. No prints. All ``Job`` fields are JSON-serializable.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Job:
    """A single background job. Mutated in place by its worker thread.

    ``cost_est`` is the local USD *estimate* for the billable run (spec
    F11/F12), set only on success when the backend reported usage. It is
    omitted from :meth:`to_dict` while ``None`` so consumers can treat an
    absent ``cost_est`` as "no estimate" (never ``$0.00`` for unknown).
    """

    id: str
    kind: str
    done: int = 0
    total: int = 0
    message: str = ""
    error: str | None = None
    cancelled: bool = False
    cost_est: float | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable snapshot of this job.

        Shape: ``{id, kind, done, total, message, error, cancelled}`` plus
        ``cost_est`` (float USD) only when a known estimate exists.
        """
        payload: dict[str, object] = {
            "id": self.id,
            "kind": self.kind,
            "done": self.done,
            "total": self.total,
            "message": self.message,
            "error": self.error,
            "cancelled": self.cancelled,
        }
        if self.cost_est is not None:
            payload["cost_est"] = self.cost_est
        return payload


_lock = threading.Lock()
_jobs: dict[str, Job] = {}
_finished: dict[str, bool] = {}
_threads: dict[str, threading.Thread] = {}


def start_job(kind: str, fn: Callable[[Job], None]) -> str:
    """Start ``fn`` in a daemon thread and return the new job id.

    ``fn`` receives the :class:`Job` object. If the function returns, the
    job is finished; if it raises, the error is captured in
    ``job.error`` and never escapes the thread.

    Raises:
        RuntimeError: If a non-finished job already exists.
    """
    with _lock:
        for job_id, done in _finished.items():
            if not done and job_id in _jobs:
                raise RuntimeError("a job is already running")
        job = Job(id=uuid.uuid4().hex, kind=kind)
        _jobs[job.id] = job
        _finished[job.id] = False

    def _run() -> None:
        try:
            fn(job)
        except Exception as exc:  # never let the exception escape the thread
            job.error = str(exc)
        finally:
            with _lock:
                _finished[job.id] = True

    thread = threading.Thread(target=_run, daemon=True)
    with _lock:
        _threads[job.id] = thread
    thread.start()
    return job.id


def get_job(job_id: str) -> Job | None:
    """Return the live :class:`Job` for ``job_id``, or None if unknown."""
    with _lock:
        return _jobs.get(job_id)


def cancel_job(job_id: str) -> bool:
    """Set the ``cancelled`` flag on the job.

    Returns True if the job exists, False if the id is unknown. The
    worker must poll ``job.cancelled`` itself; this only sets the flag.
    """
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return False
        job.cancelled = True
        return True
