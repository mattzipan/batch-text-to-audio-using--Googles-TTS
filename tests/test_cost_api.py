"""Tests for the cost-estimate wiring (spec F11/F12).

Covers the server side of the wiring half: job ``cost_est`` payloads and
messages, the ``X-Est-Cost-USD`` response header, ``GET /api/costs`` shape,
and monthly-ledger increments from mocked translate / generate / test-voice
completions. API clients are monkeypatched (no live calls) and
``XDG_DATA_HOME`` is isolated per test so the real user ledger is never
read or written.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.server as server_mod
from app import cost_ledger, jobs as jobs_mod
from app.project import set_variant_status
from app.server import create_app


@pytest.fixture()
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("WORDTAPE_DATA_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("WORDTAPE_EXPORT_DIR", str(tmp_path / "export"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("GEMINI_API_KEY", "env-key-test-0123456789")
    server_mod.current = None
    with jobs_mod._lock:
        jobs_mod._jobs.clear()
        jobs_mod._finished.clear()
        jobs_mod._threads.clear()
    yield
    server_mod.current = None
    with jobs_mod._lock:
        for job in jobs_mod._jobs.values():
            job.cancelled = True
        threads = list(jobs_mod._threads.values())
    for thread in threads:
        thread.join(timeout=5)
    with jobs_mod._lock:
        jobs_mod._jobs.clear()
        jobs_mod._finished.clear()
        jobs_mod._threads.clear()


@pytest.fixture()
def client(_isolated):
    return TestClient(create_app())


def _wait_job(job_id: str, timeout: float = 10.0) -> jobs_mod.Job:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with jobs_mod._lock:
            if jobs_mod._finished.get(job_id):
                return jobs_mod._jobs[job_id]
        time.sleep(0.02)
    raise TimeoutError(f"job {job_id} did not finish in {timeout}s")


def _new_project(client: TestClient, name: str = "demo") -> dict[str, Any]:
    resp = client.post(
        "/api/project/new",
        json={
            "name": name,
            "source_lang": "de",
            "target_lang": "id",
            "variants_enabled": True,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _import_txt(client: TestClient, content: str = "Haus\nBrot\n") -> dict[str, Any]:
    resp = client.post(
        "/api/project/import",
        json={
            "filename": "words.txt",
            "content": content,
            "kind": "txt",
            "has_header": False,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- doubles: translate ----------------------------------------------------


def _translate_with_usage(rows, *args, **kwargs):
    """Fake translate_rows that reports a known estimate (collect_costs)."""
    collect = kwargs.get("collect_costs")
    progress = kwargs.get("progress")
    out: dict[str, dict[str, str | None]] = {}
    for row in rows:
        out[row.id] = {
            "translation": f"TR-{row.source}",
            "formal": None,
            "informal": None,
        }
    if collect is not None:
        collect.append(0.004)
    if progress is not None:
        progress(len(rows), len(rows))
    return out


def _translate_without_usage(rows, *args, **kwargs):
    """Fake translate_rows whose responses carry no usage_metadata."""
    collect = kwargs.get("collect_costs")
    progress = kwargs.get("progress")
    out: dict[str, dict[str, str | None]] = {}
    for row in rows:
        out[row.id] = {
            "translation": f"TR-{row.source}",
            "formal": None,
            "informal": None,
        }
    if progress is not None:
        progress(len(rows), len(rows))
    return out


# --- doubles: generate -----------------------------------------------------


def _targets(project) -> list[tuple[str, str]]:
    return [
        (row.id, variant.id)
        for row in project.rows
        for variant in row.variants
    ]


def _generate_with_usage(
    project,
    variant_ids=None,
    force=False,
    progress=None,
    cancel=None,
    collect_cost=None,
    **kwargs,
):
    """Fake generate_audio that fills collect_cost like the real one."""
    targets = _targets(project)
    done = 0
    for row_id, variant_id in targets:
        if cancel is not None and cancel():
            break
        set_variant_status(project, row_id, variant_id, "ok")
        done += 1
        if progress is not None:
            progress(done, len(targets), f"clip {done}/{len(targets)}")
    if collect_cost is not None:
        collect_cost["usd"] = 0.0123
        collect_cost["known"] = True
    return {f"{row}:{variant}": "ok" for row, variant in targets}


def _generate_without_usage(
    project,
    variant_ids=None,
    force=False,
    progress=None,
    cancel=None,
    collect_cost=None,
    **kwargs,
):
    """Fake generate_audio run where no result carried an estimate."""
    targets = _targets(project)
    done = 0
    for row_id, variant_id in targets:
        set_variant_status(project, row_id, variant_id, "ok")
        done += 1
        if progress is not None:
            progress(done, len(targets), f"clip {done}/{len(targets)}")
    if collect_cost is not None:
        collect_cost["usd"] = 0.0
        collect_cost["known"] = False
    return {f"{row}:{variant}": "ok" for row, variant in targets}


# --- doubles: test voice ---------------------------------------------------


def _voice_known(voice, model, text, collect_cost=None, **kwargs):
    if collect_cost is not None:
        collect_cost["usd"] = 0.0004
        collect_cost["known"] = True
    return b"RIFF-fake"


def _voice_unknown(voice, model, text, collect_cost=None, **kwargs):
    if collect_cost is not None:
        collect_cost["usd"] = 0.0
        collect_cost["known"] = False
    return b"RIFF-fake"


# --- F11: job payloads carry the estimate ----------------------------------


def test_translate_job_cost_est_and_ledger_increment(client, monkeypatch, tmp_path):
    _new_project(client)
    _import_txt(client)
    monkeypatch.setattr(server_mod.translate, "translate_rows", _translate_with_usage)

    job_id = client.post("/api/translate", json={}).json()["job_id"]
    job = _wait_job(job_id)
    assert job.error is None

    payload = client.get(f"/api/jobs/{job_id}").json()
    assert payload["cost_est"] == 0.004
    assert payload["message"] == "translated 2 rows (~$0.0040 est.)"

    body = client.get("/api/costs").json()
    assert body["current"]["translate_usd"] == 0.004
    assert body["current"]["calls"] == 1
    assert body["current"]["tts_usd"] == 0.0
    assert body["history"][0]["month"] == body["current_month"]

    # The ledger landed in the isolated XDG dir — never the real one.
    path = cost_ledger.ledger_path()
    assert str(path).startswith(str(tmp_path))
    assert path.is_file()


def test_translate_without_usage_has_no_est_but_counts_a_call(client, monkeypatch):
    _new_project(client)
    _import_txt(client)
    monkeypatch.setattr(server_mod.translate, "translate_rows", _translate_without_usage)

    job_id = client.post("/api/translate", json={}).json()["job_id"]
    assert _wait_job(job_id).error is None

    payload = client.get(f"/api/jobs/{job_id}").json()
    assert "cost_est" not in payload
    assert payload["message"] == "translated 2 rows"

    body = client.get("/api/costs").json()
    assert body["current"]["translate_usd"] == 0.0
    assert body["current"]["calls"] == 1


def test_generate_job_cost_est_and_ledger_increment(client, monkeypatch):
    _new_project(client)
    _import_txt(client)
    monkeypatch.setattr(server_mod.tts, "generate_audio", _generate_with_usage)

    job_id = client.post("/api/tts/generate", json={}).json()["job_id"]
    job = _wait_job(job_id)
    assert job.error is None

    payload = client.get(f"/api/jobs/{job_id}").json()
    assert payload["cost_est"] == 0.0123
    # 0.0123 >= $0.01 -> fmt_est renders 2 decimals.
    assert payload["message"] == "clip 2/2 (~$0.01 est.)"

    body = client.get("/api/costs").json()
    assert body["current"]["tts_usd"] == 0.0123
    assert body["current"]["calls"] == 1
    assert body["current"]["translate_usd"] == 0.0


def test_generate_job_without_usage_has_no_est(client, monkeypatch):
    _new_project(client)
    _import_txt(client)
    monkeypatch.setattr(server_mod.tts, "generate_audio", _generate_without_usage)

    job_id = client.post("/api/tts/generate", json={}).json()["job_id"]
    assert _wait_job(job_id).error is None

    payload = client.get(f"/api/jobs/{job_id}").json()
    assert "cost_est" not in payload
    assert payload["message"] == "clip 2/2"

    body = client.get("/api/costs").json()
    assert body["current"]["tts_usd"] == 0.0
    assert body["current"]["calls"] == 1


def test_translate_error_does_not_record(client, monkeypatch):
    _new_project(client)
    _import_txt(client)

    def _boom(rows, *args, **kwargs):
        raise RuntimeError("translation batch 1/1 failed: fake")

    monkeypatch.setattr(server_mod.translate, "translate_rows", _boom)

    job_id = client.post("/api/translate", json={}).json()["job_id"]
    job = _wait_job(job_id)
    assert job.error is not None

    body = client.get("/api/costs").json()
    assert body["current"] == {
        "translate_usd": 0.0,
        "tts_usd": 0.0,
        "total_usd": 0.0,
        "calls": 0,
    }


# --- F11: /api/voice/test header -------------------------------------------


def test_voice_test_header_present_with_known_cost(client, monkeypatch):
    monkeypatch.setattr(server_mod.tts, "test_voice", _voice_known)
    resp = client.post(
        "/api/voice/test",
        json={"voice": "Kore", "model": "m", "text": "halo"},
    )
    assert resp.status_code == 200, resp.text
    # Bytes contract unchanged: still the WAV.
    assert resp.headers["content-type"] == "audio/wav"
    assert resp.content == b"RIFF-fake"
    raw = resp.headers.get("X-Est-Cost-USD")
    assert raw is not None
    assert isinstance(float(raw), float)
    assert float(raw) == 0.0004

    body = client.get("/api/costs").json()
    assert body["current"]["tts_usd"] == 0.0004
    assert body["current"]["calls"] == 1


def test_voice_test_header_absent_when_unknown(client, monkeypatch):
    monkeypatch.setattr(server_mod.tts, "test_voice", _voice_unknown)
    resp = client.post(
        "/api/voice/test",
        json={"voice": "Kore", "model": "m", "text": "halo"},
    )
    assert resp.status_code == 200, resp.text
    assert "X-Est-Cost-USD" not in resp.headers

    # Unknown estimate still records the completion as a $0 call.
    body = client.get("/api/costs").json()
    assert body["current"]["tts_usd"] == 0.0
    assert body["current"]["calls"] == 1


# --- F12: GET /api/costs payload -------------------------------------------


def test_costs_endpoint_payload_shape(client):
    resp = client.get("/api/costs")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {
        "current_month",
        "current",
        "history",
        "pricing_version",
        "note",
    }
    assert body["current_month"] == datetime.now().strftime("%Y-%m")
    assert set(body["current"]) == {
        "translate_usd",
        "tts_usd",
        "total_usd",
        "calls",
    }
    assert body["current"] == {
        "translate_usd": 0.0,
        "tts_usd": 0.0,
        "total_usd": 0.0,
        "calls": 0,
    }
    assert body["history"] == []  # empty ledger -> empty state upstream
    assert body["pricing_version"] == "2026-09-22+intro"
    assert body["note"] == (
        "Estimates from usageMetadata × Standard-tier table. "
        "Authoritative spend: AI Studio Billing."
    )
    # Nothing sensitive may leak into the payload.
    assert os.environ["GEMINI_API_KEY"] not in resp.text
    assert "gemini_api_key" not in resp.text
