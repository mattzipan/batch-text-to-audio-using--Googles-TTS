"""Tests for app/jobs.py (spec task B4)."""

import json
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import jobs  # noqa: E402
from app.jobs import Job, cancel_job, get_job, start_job  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_registry():
    with jobs._lock:
        jobs._jobs.clear()
        jobs._finished.clear()
        jobs._threads.clear()
    yield
    with jobs._lock:
        for job in jobs._jobs.values():
            job.cancelled = True
        threads = list(jobs._threads.values())
    for thread in threads:
        thread.join(timeout=5)
    with jobs._lock:
        jobs._jobs.clear()
        jobs._finished.clear()
        jobs._threads.clear()


def _wait_finished(job_id: str, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while True:
        with jobs._lock:
            if jobs._finished.get(job_id, False):
                return
        if time.time() > deadline:
            raise TimeoutError(f"job {job_id} did not finish in {timeout}s")
        time.sleep(0.01)


def test_progress_visible_while_running():
    started = threading.Event()
    release = threading.Event()

    def fn(job: Job) -> None:
        job.total = 2
        job.done = 1
        job.message = "working"
        started.set()
        assert release.wait(timeout=5)

    job_id = start_job("demo", fn)
    assert started.wait(timeout=5)

    seen = get_job(job_id)
    assert seen is not None
    assert (seen.done, seen.total, seen.message) == (1, 2, "working")
    assert seen.error is None
    assert seen.cancelled is False

    release.set()
    _wait_finished(job_id)


def test_cancel_flag_stops_polling_fn():
    stopped = threading.Event()

    def fn(job: Job) -> None:
        job.total = 100
        for i in range(100):
            if job.cancelled:
                stopped.set()
                return
            job.done = i + 1
            time.sleep(0.01)

    job_id = start_job("demo", fn)
    time.sleep(0.05)
    assert cancel_job(job_id) is True
    assert stopped.wait(timeout=5)
    assert get_job(job_id) is not None
    assert get_job(job_id).cancelled is True
    _wait_finished(job_id)


def test_cancel_unknown_job_returns_false():
    assert cancel_job("no-such-job") is False
    assert get_job("no-such-job") is None


def test_second_start_while_running_raises():
    release = threading.Event()

    def fn(job: Job) -> None:
        assert release.wait(timeout=5)

    first_id = start_job("first", fn)
    with pytest.raises(RuntimeError, match="a job is already running"):
        start_job("second", lambda job: None)

    release.set()
    _wait_finished(first_id)

    # After the first job finishes, starting a new one works again.
    third_id = start_job("third", lambda job: None)
    _wait_finished(third_id)
    assert get_job(third_id) is not None


def test_exception_captured_in_error():
    def fn(job: Job) -> None:
        job.total = 1
        raise ValueError("boom")

    job_id = start_job("fail", fn)
    _wait_finished(job_id)

    seen = get_job(job_id)
    assert seen is not None
    assert seen.error == "boom"


def test_to_dict_is_json_serializable():
    job = Job(
        id="abc123",
        kind="demo",
        done=1,
        total=2,
        message="halfway",
        error=None,
        cancelled=False,
    )
    payload = job.to_dict()
    assert payload == {
        "id": "abc123",
        "kind": "demo",
        "done": 1,
        "total": 2,
        "message": "halfway",
        "error": None,
        "cancelled": False,
    }
    assert json.dumps(payload)

    # A real (errored, cancelled) job snapshot must also round-trip.
    def fn(job: Job) -> None:
        raise RuntimeError("kaput")

    job_id = start_job("fail", fn)
    _wait_finished(job_id)
    cancel_job(job_id)
    assert json.dumps(get_job(job_id).to_dict())
