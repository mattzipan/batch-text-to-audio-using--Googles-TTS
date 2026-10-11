"""Tests for app/server.py + app/boot.py (spec tasks C1/C2).

Uses ``TestClient`` against :func:`app.server.create_app` with the service
modules monkeypatched (fast fakes that drive job progress). The jobs registry,
the active project, and ``HOME`` (projects live under ``~/WordTape``) are all
isolated per test.
"""

from __future__ import annotations

import threading
from pathlib import Path
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.server as server_mod
from app import jobs as jobs_mod
from app.boot import find_free_port, start_server_thread, wait_until_up
from app.project import set_variant_status
from app.server import create_app
from backends.base import VoiceInfo


@pytest.fixture()
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("WORDTAPE_DATA_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("WORDTAPE_EXPORT_DIR", str(tmp_path / "export"))
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


def _fake_translate(rows, *args, **kwargs):
    progress = kwargs.get("progress")
    out: dict[str, dict[str, str | None]] = {}
    done = 0
    for row in rows:
        done += 1
        out[row.id] = {
            "translation": f"TR-{row.source}",
            "formal": f"F-{row.source}",
            "informal": None,
        }
    if progress is not None:
        progress(done, len(rows))
    return out


def _fake_generate(project, variant_ids=None, force=False, progress=None,
                   cancel=None, **kwargs):
    targets = [
        (row.id, variant.id) for row in project.rows for variant in row.variants
    ]
    done = 0
    for row_id, variant_id in targets:
        if cancel is not None and cancel():
            break
        set_variant_status(project, row_id, variant_id, "ok")
        done += 1
        if progress is not None:
            progress(done, len(targets), f"clip {done}/{len(targets)}")
    return {}


def _rows(client: TestClient) -> list[dict[str, Any]]:
    resp = client.get("/api/state")
    assert resp.status_code == 200, resp.text
    return resp.json()["rows"]


# --- guards / state -------------------------------------------------------


def test_state_empty_and_guards(client):
    resp = client.get("/api/state")
    assert resp.status_code == 200
    assert resp.json()["project"] is None

    resp = client.get("/")
    assert resp.status_code == 200
    if "application/json" in resp.headers.get("content-type", ""):
        assert resp.json() == {"app": "WordTape", "status": "no frontend yet"}

    assert client.post("/api/rows", json={"source": "x"}).status_code == 409
    assert client.post("/api/translate", json={}).status_code == 409
    assert client.post("/api/tts/generate", json={}).status_code == 409
    assert client.post("/api/track/build").status_code == 409
    assert client.get("/api/track").status_code == 409
    assert client.get("/media/audio/x.wav").status_code == 409


def test_project_new_validation(client):
    bad = client.post("/api/project/new", json={"name": "bad name!"})
    assert bad.status_code == 400
    assert bad.json() == {"detail": bad.json()["detail"]}

    ok = client.post("/api/project/new", json={"name": "demo"})
    assert ok.status_code == 200
    assert ok.json()["project"]["name"] == "demo"

    dup = client.post("/api/project/new", json={"name": "demo"})
    assert dup.status_code == 409


def test_project_open_roundtrip(client):
    state = _new_project(client)
    path = state["project"]["path"]
    _import_txt(client)

    server_mod.current = None
    reopened = client.post("/api/project/open", json={"path": path})
    assert reopened.status_code == 200
    assert [row["source"] for row in reopened.json()["rows"]] == ["Haus", "Brot"]

    missing = client.post("/api/project/open", json={"path": "/no/such/dir"})
    assert missing.status_code == 404


# --- import ---------------------------------------------------------------


def test_import_txt_replaces_rows(client):
    _new_project(client)
    body = _import_txt(client, "Haus\n\nBrot\n")
    assert body == {"imported": 2}
    rows = _rows(client)
    assert [row["source"] for row in rows] == ["Haus", "Brot"]
    assert [row["position"] for row in rows] == [1, 2]
    for row in rows:
        assert len(row["variants"]) == 1
        assert row["variants"][0]["style"] == "main"
        assert row["variants"][0]["text"] == ""
        assert row["variants"][0]["status"] == "pending"


def test_import_semicolon_csv_with_bom_and_header(client):
    _new_project(client)
    content = "\ufeffsource;translation\nHaus;Rumah\nBrot;Roti\n"
    resp = client.post(
        "/api/project/import",
        json={
            "filename": "words.csv",
            "content": content,
            "kind": "csv",
            "has_header": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"imported": 2}
    rows = _rows(client)
    assert [(row["source"], row["variants"][0]["text"]) for row in rows] == [
        ("Haus", "Rumah"),
        ("Brot", "Roti"),
    ]


def test_import_errors(client):
    _new_project(client)
    bad_kind = client.post(
        "/api/project/import",
        json={"filename": "w", "content": "x", "kind": "xls", "has_header": False},
    )
    assert bad_kind.status_code == 400
    bad_csv = client.post(
        "/api/project/import",
        json={
            "filename": "w.csv",
            "content": "only-one-column\nanother\n",
            "kind": "csv",
            "has_header": False,
        },
    )
    assert bad_csv.status_code == 400


# --- jobs: translate / tts / track ----------------------------------------


def test_translate_job_fills_main_and_variants(client, monkeypatch):
    _new_project(client)
    _import_txt(client)
    monkeypatch.setattr(server_mod.translate, "translate_rows", _fake_translate)

    resp = client.post("/api/translate", json={})
    assert resp.status_code == 200, resp.text
    job = _wait_job(resp.json()["job_id"])
    assert job.error is None
    assert (job.done, job.total) == (2, 2)

    rows = _rows(client)
    assert rows[0]["variants"][0]["text"] == "TR-Haus"
    styles = {variant["style"] for row in rows for variant in row["variants"]}
    assert styles == {"main", "formal"}  # informal was None -> not created
    formal = next(
        variant
        for variant in rows[0]["variants"]
        if variant["style"] == "formal"
    )
    assert formal["text"] == "F-Haus"
    assert formal["status"] == "pending"


def test_translate_row_ids_subset(client, monkeypatch):
    _new_project(client)
    _import_txt(client, "Haus\nBrot\nKase\n")
    monkeypatch.setattr(server_mod.translate, "translate_rows", _fake_translate)

    rows = _rows(client)
    resp = client.post("/api/translate", json={"row_ids": [rows[0]["id"]]})
    assert resp.status_code == 200, resp.text
    assert _wait_job(resp.json()["job_id"]).error is None

    rows = _rows(client)
    assert rows[0]["variants"][0]["text"] == "TR-Haus"
    assert rows[1]["variants"][0]["text"] == ""

    unknown = client.post("/api/translate", json={"row_ids": ["abcdef"]})
    assert unknown.status_code == 404


def test_tts_generate_job_marks_ok(client, monkeypatch):
    _new_project(client)
    _import_txt(client)
    monkeypatch.setattr(server_mod.translate, "translate_rows", _fake_translate)
    monkeypatch.setattr(server_mod.tts, "generate_audio", _fake_generate)

    translate_id = client.post("/api/translate", json={}).json()["job_id"]
    assert _wait_job(translate_id).error is None

    resp = client.post("/api/tts/generate", json={"force": False})
    assert resp.status_code == 200, resp.text
    job = _wait_job(resp.json()["job_id"])
    assert job.error is None
    assert job.message == "clip 4/4"

    rows = _rows(client)
    assert all(
        variant["status"] == "ok" for row in rows for variant in row["variants"]
    )


def test_track_build_and_info(client, monkeypatch):
    _new_project(client)
    _import_txt(client)
    monkeypatch.setattr(server_mod.translate, "translate_rows", _fake_translate)
    monkeypatch.setattr(server_mod.tts, "generate_audio", _fake_generate)

    def _fake_build(project, included, repeats=5, repeat_gap_s=1.2,
                    item_gap_s=1.8, out_dir=None, **kwargs):
        from app import config as _cfg
        out = out_dir or _cfg.export_dir(project.folder.name)
        out.mkdir(parents=True, exist_ok=True)
        (out / "final.wav").write_bytes(b"wav-bytes")
        (out / "final.mp3").write_bytes(b"mp3-bytes")
        return {
            "wav": str(out / "final.wav"),
            "mp3": str(out / "final.mp3"),
            "duration_s": 9.5,
        }

    def _fake_estimate(project, included, repeats=5, repeat_gap_s=1.2,
                       item_gap_s=1.8):
        return 7.25

    monkeypatch.setattr(server_mod.assembler, "build_track", _fake_build)
    monkeypatch.setattr(server_mod.assembler, "estimate_duration", _fake_estimate)

    assert _wait_job(client.post("/api/translate", json={}).json()["job_id"]).error is None
    assert _wait_job(client.post("/api/tts/generate", json={}).json()["job_id"]).error is None

    resp = client.post("/api/track/build")
    assert resp.status_code == 200, resp.text
    assert _wait_job(resp.json()["job_id"]).error is None

    info = client.get("/api/track")
    assert info.status_code == 200, info.text
    body = info.json()
    assert body["exists"] is True
    assert body["wav_url"] == "/export/final.wav"
    assert body["mp3_url"] == "/export/final.mp3"
    assert body["duration_s"] == 7.25
    assert Path(body["output_dir"]).name == "demo"

    media = client.get("/export/final.mp3")
    assert media.status_code == 200
    assert media.content == b"mp3-bytes"


# --- row ops --------------------------------------------------------------


def test_row_patch_marks_stale(client, monkeypatch):
    _new_project(client)
    _import_txt(client)
    monkeypatch.setattr(server_mod.translate, "translate_rows", _fake_translate)
    monkeypatch.setattr(server_mod.tts, "generate_audio", _fake_generate)
    assert _wait_job(client.post("/api/translate", json={}).json()["job_id"]).error is None
    assert _wait_job(client.post("/api/tts/generate", json={}).json()["job_id"]).error is None

    rows = _rows(client)
    row_id = rows[0]["id"]
    main_id = rows[0]["variants"][0]["id"]

    resp = client.patch(
        f"/api/rows/{row_id}", json={"variants": [{"id": main_id, "text": "Rumah edit"}]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["variants"][0]["status"] == "stale"

    state_rows = _rows(client)
    assert state_rows[0]["variants"][0]["text"] == "Rumah edit"
    assert state_rows[0]["variants"][0]["status"] == "stale"

    resp = client.patch(f"/api/rows/{row_id}", json={"source": "Haus edit"})
    assert resp.status_code == 200, resp.text
    assert all(variant["status"] == "stale" for variant in resp.json()["variants"])

    assert client.patch("/api/rows/abcdef", json={"source": "x"}).status_code == 404


def test_row_insert_delete_move(client):
    _new_project(client)
    _import_txt(client, "eins\nzwei\n")
    rows = _rows(client)
    first, second = rows[0]["id"], rows[1]["id"]

    end = client.post("/api/rows", json={"source": "drei"})
    assert end.status_code == 200, end.text
    assert [row["source"] for row in _rows(client)] == ["eins", "zwei", "drei"]

    mid = client.post(
        "/api/rows",
        json={"after_row_id": first, "source": "einhalb", "translation": "setengah"},
    )
    assert mid.status_code == 200, mid.text
    assert [row["source"] for row in _rows(client)] == ["eins", "einhalb", "zwei", "drei"]

    moved = client.post(f"/api/rows/{second}/move", json={"direction": "down"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["moved"] is True
    assert [row["source"] for row in _rows(client)] == ["eins", "einhalb", "drei", "zwei"]

    bad_dir = client.post(f"/api/rows/{second}/move", json={"direction": "sideways"})
    assert bad_dir.status_code == 400

    deleted = client.delete(f"/api/rows/{first}")
    assert deleted.status_code == 200, deleted.text
    remaining = _rows(client)
    assert [row["source"] for row in remaining] == ["einhalb", "drei", "zwei"]
    assert [row["position"] for row in remaining] == [1, 2, 3]

    assert client.delete("/api/rows/abcdef").status_code == 404


# --- voices ---------------------------------------------------------------


def test_voices_passthrough(client, monkeypatch):
    seen: dict[str, Any] = {}

    def _fake_list(model=None, language=None, **kwargs):
        seen["model"] = model
        seen["language"] = language
        return [VoiceInfo(name="Kore", gender="FEMALE", languages=["id-ID"])]

    monkeypatch.setattr(server_mod.tts, "list_voices", _fake_list)
    resp = client.get("/api/voices", params={"model": "m", "language": "id"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == [
        {"name": "Kore", "gender": "FEMALE", "languages": ["id-ID"], "note": None}
    ]
    assert seen == {"model": "m", "language": "id"}


def test_voice_test_returns_wav(client, monkeypatch):
    monkeypatch.setattr(
        server_mod.tts, "test_voice", lambda voice, model, text: b"RIFF-fake"
    )
    resp = client.post(
        "/api/voice/test",
        json={"voice": "Kore", "model": "m", "text": "halo"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "audio/wav"
    assert resp.content == b"RIFF-fake"


# --- media guard / jobs ---------------------------------------------------


def test_media_traversal_blocked(client):
    _new_project(client)
    assert client.get("/media/../../etc/passwd").status_code == 404
    assert client.get("/media/output/missing.wav").status_code == 404


def test_second_job_conflicts_and_cancel(client, monkeypatch):
    _new_project(client)
    _import_txt(client)
    started = threading.Event()
    release = threading.Event()

    def _blocking(rows, *args, **kwargs):
        cancel = kwargs.get("cancel")
        started.set()
        while not release.wait(0.02):
            if cancel is not None and cancel():
                return {}
        return {row.id: {"translation": "x", "formal": None, "informal": None} for row in rows}

    monkeypatch.setattr(server_mod.translate, "translate_rows", _blocking)

    first = client.post("/api/translate", json={})
    assert first.status_code == 200, first.text
    assert started.wait(timeout=5)
    job_id = first.json()["job_id"]

    assert client.post("/api/translate", json={}).status_code == 409
    assert client.post("/api/tts/generate", json={}).status_code == 409
    assert client.post("/api/track/build").status_code == 409

    cancelled = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json() == {"cancelled": True}
    assert client.get(f"/api/jobs/{job_id}").json()["cancelled"] is True

    release.set()
    assert _wait_job(job_id).error is None
    assert client.get("/api/jobs/no-such-job").status_code == 404


# --- boot helpers ---------------------------------------------------------


def test_boot_find_port_and_wait_timeout():
    port = find_free_port()
    assert isinstance(port, int) and port > 0
    assert wait_until_up(f"http://127.0.0.1:{port}/nope", timeout=0.5) is False


def test_boot_server_thread_serves():
    port = find_free_port()
    thread = start_server_thread(create_app(), port)
    try:
        assert wait_until_up(f"http://127.0.0.1:{port}/", timeout=10.0) is True
        assert thread.is_alive()
    finally:
        thread.join(timeout=0.1)


# --- project settings / estimate / build inclusion -------------------------


def test_project_settings_patch(client):
    assert client.patch("/api/project/settings", json={"repeats": 5}).status_code == 409

    _new_project(client)
    resp = client.patch(
        "/api/project/settings",
        json={
            "repeats": 3,
            "repeat_gap_s": 0.5,
            "item_gap_s": 2.5,
            "voice": "Puck",
            "tts_model": "gemini-3.8-flash-tts",
        },
    )
    assert resp.status_code == 200, resp.text
    meta = resp.json()
    assert meta["repeats"] == 3
    assert meta["repeat_gap_s"] == 0.5
    assert meta["item_gap_s"] == 2.5
    assert meta["voice"] == "Puck"
    assert meta["tts_model"] == "gemini-3.8-flash-tts"

    state = client.get("/api/state").json()
    assert state["project"]["repeats"] == 3
    assert state["project"]["voice"] == "Puck"

    # Partial update keeps the rest.
    partial = client.patch("/api/project/settings", json={"repeats": 7})
    assert partial.status_code == 200, partial.text
    assert partial.json()["repeats"] == 7
    assert partial.json()["voice"] == "Puck"

    for bad in (
        {"repeats": 0},
        {"repeats": 11},
        {"repeats": "many"},
        {"repeat_gap_s": -1},
        {"repeat_gap_s": 61},
        {"item_gap_s": "long"},
        {"voice": ""},
        {"tts_model": ""},
        {"bogus": 1},
    ):
        assert client.patch("/api/project/settings", json=bad).status_code == 400


def test_track_estimate(client, monkeypatch):
    _new_project(client)
    _import_txt(client)

    # Nothing ok yet -> empty inclusion -> 0.0 without touching audio files.
    resp = client.get("/api/track/estimate")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"duration_s": 0.0}

    # Estimate errors (e.g. missing/corrupt cache) surface as null.
    def _boom(project, included, **kwargs):
        raise ValueError("bad clip")

    monkeypatch.setattr(server_mod.assembler, "estimate_duration", _boom)
    resp = client.get("/api/track/estimate")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"duration_s": None}

    # The included filter is forwarded to the estimator as pairs.
    seen: dict[str, Any] = {}

    def _capture(project, included, **kwargs):
        seen["included"] = list(included)
        return 5.0

    monkeypatch.setattr(server_mod.assembler, "estimate_duration", _capture)
    resp = client.get("/api/track/estimate", params={"included": "aa:bb,cc:dd"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"duration_s": 5.0}
    assert seen["included"] == [("aa", "bb"), ("cc", "dd")]

    assert client.get("/api/track/estimate", params={"included": "no-colon"}).status_code == 400


def test_track_build_with_included(client, monkeypatch):
    _new_project(client)
    _import_txt(client)

    seen: dict[str, Any] = {}

    def _fake_build(project, included, **kwargs):
        seen["included"] = list(included)
        return {"wav": "w", "mp3": "m", "duration_s": 1.0}

    monkeypatch.setattr(server_mod.assembler, "build_track", _fake_build)

    wanted = ["aa:bb", "cc:dd"]
    resp = client.post("/api/track/build", json={"included": wanted})
    assert resp.status_code == 200, resp.text
    assert _wait_job(resp.json()["job_id"]).error is None
    assert seen["included"] == [("aa", "bb"), ("cc", "dd")]

    bad = client.post("/api/track/build", json={"included": ["no-colon"]})
    assert bad.status_code == 400
