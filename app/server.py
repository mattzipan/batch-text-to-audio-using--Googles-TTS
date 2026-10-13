"""WordTape HTTP server (spec tasks C1): FastAPI app, project state, jobs.

One active project is held in module state (:data:`current`), mutated only
via :mod:`app.project` operations followed by :func:`app.project.save_project`.
Long-running work (translate / TTS / track build) runs as :mod:`app.jobs` jobs.

Service modules (:mod:`app.translate`, :mod:`app.tts`, :mod:`app.assembler`,
:mod:`app.importer`) are imported as modules so tests can monkeypatch them.
"""

from __future__ import annotations

import dataclasses
import os
import re
import secrets
import subprocess
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app import (
    assembler,
    config,
    cost_ledger,
    costs,
    importer,
    jobs,
    settings_store,
    translate,
    tts,
)
from app import project as projects
from app.project import Project, Row, Variant

current: Project | None = None
"""The single active project (``None`` when no project is open)."""

_state_lock = threading.Lock()

_NAME_RE = re.compile(r"[A-Za-z0-9_-]+")

_DEFAULT_TTS_MODEL = "gemini-3.8-flash-lite-tts"

#: Size cap for path-based imports (the local-server analogue of a sane
#: upload limit; word lists are tiny).
_IMPORT_MAX_BYTES = 5 * 1024 * 1024


def _read_import_path(path: Any) -> tuple[str, str]:
    """Resolve a server-side import file path to ``(kind, content)``.

    Used by the webview drop/pick flow, where the browser sandbox cannot read
    the file so the localhost server reads it from disk instead. Validates
    extension (``.txt``/``.csv``), existence, and size before decoding as
    ``utf-8-sig`` (the same decode the browser-upload path uses).
    """
    if not isinstance(path, str) or not path.strip():
        raise HTTPException(
            status_code=400, detail="path must be a non-empty string"
        )
    file = Path(path)
    suffix = file.suffix.lower()
    if suffix == ".txt":
        kind = "txt"
    elif suffix == ".csv":
        kind = "csv"
    else:
        raise HTTPException(
            status_code=400, detail="unsupported file type; use a .txt or .csv file"
        )
    if not file.exists() or not file.is_file():
        raise HTTPException(status_code=404, detail=f"file not found: {path}")
    if file.stat().st_size > _IMPORT_MAX_BYTES:
        raise HTTPException(status_code=400, detail="file is too large (max 5 MB)")
    try:
        data = file.read_bytes()
    except OSError as exc:
        raise HTTPException(
            status_code=400, detail=f"could not read file: {exc}"
        ) from exc
    return kind, data.decode("utf-8-sig", errors="replace")


def projects_root() -> Path:
    """Return the projects directory (inside the app folder; created on demand)."""
    return config.projects_root()


async def _body(request: Request) -> dict[str, Any]:
    """Return the JSON body as a dict (``{}`` when absent or unparseable)."""
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _require_project() -> Project:
    if current is None:
        raise HTTPException(
            status_code=409, detail="no project open; create or open one first"
        )
    return current


def _variant_to_dict(variant: Variant) -> dict[str, Any]:
    return {
        "id": variant.id,
        "style": variant.style,
        "text": variant.text,
        "audio": variant.audio,
        "status": variant.status,
    }


def _row_to_dict(row: Row) -> dict[str, Any]:
    return {
        "id": row.id,
        "position": row.position,
        "source": row.source,
        "variants": [_variant_to_dict(v) for v in row.variants],
    }


def _project_meta(proj: Project) -> dict[str, Any]:
    return {
        "name": proj.folder.name,
        "path": str(proj.folder),
        "source_lang": proj.source_lang,
        "target_lang": proj.target_lang,
        "variants_enabled": proj.variants_enabled,
        "tts_model": proj.tts_model,
        "voice": proj.voice,
        "repeats": proj.repeats,
        "repeat_gap_s": proj.repeat_gap_s,
        "item_gap_s": proj.item_gap_s,
    }


def _track_info(proj: Project) -> dict[str, Any]:
    out_dir = config.export_dir(proj.folder.name)
    wav = out_dir / "final.wav"
    mp3 = out_dir / "final.mp3"
    included = [
        (row.id, variant.id)
        for row in proj.rows
        for variant in row.variants
        if variant.status == "ok"
    ]
    duration: float | None = None
    if included:
        try:
            duration = float(
                assembler.estimate_duration(
                    proj,
                    included,
                    repeats=proj.repeats,
                    repeat_gap_s=proj.repeat_gap_s,
                    item_gap_s=proj.item_gap_s,
                )
            )
        except Exception:
            duration = None
    return {
        "exists": wav.is_file() and mp3.is_file(),
        "wav_url": "/export/final.wav" if wav.is_file() else None,
        "mp3_url": "/export/final.mp3" if mp3.is_file() else None,
        "duration_s": duration,
        "output_dir": str(out_dir),
    }


def _settings_payload() -> dict[str, Any]:
    """GET/PATCH /api/settings response shape (never includes the full key)."""
    key: str | None
    try:
        key = config.get_api_key()
    except RuntimeError:
        key = None
    return {
        "has_key": key is not None,
        "key_hint": ("…" + key[-4:]) if key is not None and len(key) > 4 else None,
        "export_root": settings_store.load().get("export_root"),
        "export_default": str(config.default_export_root()),
    }


def _launch_reveal(path: Path) -> tuple[bool, bool]:
    """Fire-and-forget a file-manager reveal; return (opened, selected).

    Tries ``nautilus --select``, then ``nemo --select``, then
    ``xdg-open <folder>`` (selected=False on the xdg-open fallback).
    Never blocks: plain ``Popen`` without ``check``/``capture_output``.
    """
    folder = path if path.is_dir() else path.parent
    attempts: list[tuple[list[str], bool]] = [
        (["nautilus", "--select", str(path)], True),
        (["nemo", "--select", str(path)], True),
        (["xdg-open", str(folder)], False),
    ]
    for argv, selects in attempts:
        try:
            subprocess.Popen(
                argv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            continue
        return True, selects
    return False, False


def state_payload() -> dict[str, Any]:
    """Return the full UI state for the active project (or an empty one)."""
    proj = current
    if proj is None:
        return {"project": None, "rows": []}
    return {
        "project": _project_meta(proj),
        "rows": [_row_to_dict(row) for row in proj.rows],
        "track": _track_info(proj),
    }


def _voice_to_dict(voice: Any) -> Any:
    if isinstance(voice, dict):
        return voice
    if dataclasses.is_dataclass(voice) and not isinstance(voice, type):
        return dataclasses.asdict(voice)
    return {
        "name": getattr(voice, "name", str(voice)),
        "gender": getattr(voice, "gender", None),
        "languages": getattr(voice, "languages", []),
        "note": getattr(voice, "note", None),
    }


def _fresh_variant_id(taken: set[str]) -> str:
    while True:
        candidate = secrets.token_hex(3)
        if candidate not in taken:
            taken.add(candidate)
            return candidate


def _ensure_variant(proj: Project, row: Row, style: str, taken: set[str]) -> Variant:
    """Return the row's variant of ``style``, creating it (pending) if missing."""
    for variant in row.variants:
        if variant.style == style:
            return variant
    variant_id = _fresh_variant_id(taken)
    variant = Variant(
        id=variant_id,
        style=style,
        text="",
        audio=f"audio/{row.id}_{variant_id}.wav",
        status="pending",
    )
    row.variants.append(variant)
    return variant


def _remove_variant(proj: Project, row: Row, style: str) -> None:
    """Drop the row's variant of ``style`` (if any) and its cached audio."""
    for index, variant in enumerate(row.variants):
        if variant.style == style:
            projects.audio_path(proj, row.id, variant.id).unlink(missing_ok=True)
            del row.variants[index]
            return


def _translate_run(wanted: list[str] | None, job: jobs.Job) -> None:
    proj = current
    if proj is None:
        raise RuntimeError("no project open")
    if wanted is not None:
        targets = [row for row in proj.rows if row.id in set(wanted)]
    else:
        targets = [
            row
            for row in proj.rows
            if any(variant.status == "pending" for variant in row.variants)
        ]
    job.total = len(targets)
    job.done = 0
    job.message = f"translating 0/{len(targets)}"
    if not targets:
        job.message = "nothing to translate"
        return

    def _progress(done: int, total: int) -> None:
        job.done = done
        job.total = total
        job.message = f"translating {done}/{total}"

    collect_costs: list[float] = []
    mapping = translate.translate_rows(
        targets,
        proj.source_lang,
        proj.target_lang,
        proj.variants_enabled,
        progress=_progress,
        cancel=lambda: job.cancelled,
        collect_costs=collect_costs,
    )
    total = round(sum(collect_costs), 6)
    known = bool(collect_costs)
    with _state_lock:
        taken: set[str] = set()
        for row in proj.rows:
            taken.add(row.id)
            for variant in row.variants:
                taken.add(variant.id)
        for row in targets:
            entry = mapping.get(row.id) or {}
            main = _ensure_variant(proj, row, "main", taken)
            raw = entry.get("translation")
            main.text = "" if raw is None else str(raw)
            main.status = "pending"
            if proj.variants_enabled:
                for style in ("formal", "informal"):
                    value = entry.get(style)
                    if value:
                        variant = _ensure_variant(proj, row, style, taken)
                        variant.text = str(value)
                        variant.status = "pending"
                    else:
                        # Model returned no register variant: drop any stale
                        # one (e.g. previously stored in the wrong language)
                        # so a re-run repairs the row.
                        _remove_variant(proj, row, style)
        projects.save_project(proj)
    job.done = len(targets)
    job.message = f"translated {len(targets)} rows"
    if known:
        job.cost_est = total
        job.message = (
            f"translated {len(targets)} rows ({costs.fmt_est(total)} est.)"
        )
    # One ledger write per completed run; unknown estimates still count as a
    # call (with 0). Runs that made no API call (nothing to translate) and
    # errored/cancelled-by-exception runs never reach this line.
    _record_cost("translate", total if known else 0.0)


def _tts_run(
    variant_ids: list[str] | None, force: bool, job: jobs.Job
) -> None:
    proj = current
    if proj is None:
        raise RuntimeError("no project open")

    attempted = False

    def _progress(done: int, total: int, message: str = "") -> None:
        nonlocal attempted
        attempted = True
        job.done = done
        job.total = total
        job.message = message

    collect_cost: dict[str, Any] = {}
    tts.generate_audio(
        proj,
        variant_ids=variant_ids,
        force=force,
        progress=_progress,
        cancel=lambda: job.cancelled,
        collect_cost=collect_cost,
    )
    with _state_lock:
        projects.save_project(proj)
    known = bool(collect_cost.get("known"))
    total = round(float(collect_cost.get("usd") or 0.0), 6)
    if known:
        job.cost_est = total
        est = f"({costs.fmt_est(total)} est.)"
        job.message = f"{job.message} {est}".strip() if job.message else est
    # Record only when at least one synthesis attempt happened (progress fired
    # or an estimate came back) — a no-op run spends nothing, so it is not a
    # billable completion. Unknown estimates still count as a call at $0.
    if attempted or known:
        _record_cost("tts", total if known else 0.0)


def _track_run(job: jobs.Job, wanted: list[tuple[str, str]] | None = None) -> None:
    proj = current
    if proj is None:
        raise RuntimeError("no project open")
    if wanted is None:
        included = [
            (row.id, variant.id)
            for row in proj.rows
            for variant in row.variants
            if variant.status == "ok"
        ]
    else:
        included = list(wanted)
    job.total = len(included)
    job.done = 0
    job.message = "building track"
    assembler.build_track(
        proj,
        included,
        repeats=proj.repeats,
        repeat_gap_s=proj.repeat_gap_s,
        item_gap_s=proj.item_gap_s,
        out_dir=config.export_dir(proj.folder.name),
    )
    with _state_lock:
        projects.save_project(proj)
    job.done = len(included)
    job.message = "track built"


def _start_job_or_409(kind: str, fn: Any) -> str:
    try:
        return jobs.start_job(kind, fn)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _record_cost(kind: str, usd: float) -> None:
    """One best-effort ledger write per billable completion (spec F12).

    Wrapped so a ledger failure can never fail the job itself;
    :func:`app.cost_ledger.record` also never raises.
    """
    try:
        cost_ledger.record(kind, usd)
    except Exception:  # noqa: BLE001 - the ledger is best-effort by design
        pass


def create_app() -> FastAPI:
    """Build the WordTape FastAPI application."""
    app = FastAPI(title=config.APP_NAME)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, HTTPException):
            return JSONResponse(
                status_code=exc.status_code, content={"detail": exc.detail}
            )
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc) or "internal server error"},
        )

    @app.get("/api/state")
    def api_state() -> dict[str, Any]:
        return state_payload()

    @app.post("/api/project/new")
    async def api_project_new(request: Request) -> dict[str, Any]:
        global current
        body = await _body(request)
        name = body.get("name", "")
        if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
            raise HTTPException(
                status_code=400,
                detail="project name must match [A-Za-z0-9_-]+",
            )
        source_lang = body.get("source_lang", config.DEFAULT_SOURCE_LANG)
        target_lang = body.get("target_lang", config.DEFAULT_TARGET_LANG)
        variants_enabled = bool(body.get("variants_enabled", False))
        folder = projects_root() / name
        if (folder / "project.json").is_file():
            raise HTTPException(
                status_code=409, detail=f"project {name!r} already exists"
            )
        with _state_lock:
            proj = projects.new_project(folder, source_lang, target_lang, variants_enabled)
            projects.save_project(proj)
            current = proj
        return state_payload()

    @app.post("/api/project/open")
    async def api_project_open(request: Request) -> dict[str, Any]:
        global current
        body = await _body(request)
        raw = body.get("path", "")
        if not isinstance(raw, str) or not raw:
            raise HTTPException(status_code=400, detail="path is required")
        folder = Path(raw).expanduser()
        if not folder.is_absolute():
            folder = Path.cwd() / folder
        if not (folder / "project.json").is_file():
            raise HTTPException(
                status_code=404, detail=f"no project found at {raw!r}"
            )
        try:
            proj = projects.load_project(folder)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        with _state_lock:
            current = proj
        return state_payload()

    @app.post("/api/project/import")
    async def api_project_import(request: Request) -> dict[str, Any]:
        proj = _require_project()
        body = await _body(request)
        path = body.get("path")
        content = body.get("content")
        has_header = bool(body.get("has_header", False))
        if (path is None) == (content is None):
            raise HTTPException(
                status_code=400,
                detail='provide exactly one of "content" or "path"',
            )
        if path is not None:
            kind, content = _read_import_path(path)
        else:
            kind = body.get("kind", "")
            if kind not in ("txt", "csv"):
                raise HTTPException(
                    status_code=400, detail='kind must be "txt" or "csv"'
                )
            if not isinstance(content, str):
                raise HTTPException(
                    status_code=400, detail="content must be a string"
                )
        try:
            if kind == "txt":
                pairs: list[tuple[str, str | None]] = [
                    (term, None) for term in importer.parse_txt(content)
                ]
            else:
                pairs = [
                    (source, translation)
                    for source, translation in importer.parse_csv(
                        content, has_header
                    )
                ]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        with _state_lock:
            proj.rows.clear()
            for source, translation in pairs:
                projects.insert_row(proj, None, source, translation)
            projects.save_project(proj)
        return {"imported": len(pairs)}

    @app.post("/api/translate")
    async def api_translate(request: Request) -> dict[str, Any]:
        proj = _require_project()
        body = await _body(request)
        row_ids = body.get("row_ids")
        wanted: list[str] | None = None
        if row_ids is not None:
            if not isinstance(row_ids, list) or not all(
                isinstance(item, str) for item in row_ids
            ):
                raise HTTPException(
                    status_code=400, detail="row_ids must be a list of row ids"
                )
            known = {row.id for row in proj.rows}
            unknown = [item for item in row_ids if item not in known]
            if unknown:
                raise HTTPException(
                    status_code=404, detail=f"unknown row ids: {unknown}"
                )
            wanted = list(row_ids)
        job_id = _start_job_or_409("translate", lambda job: _translate_run(wanted, job))
        return {"job_id": job_id}

    @app.patch("/api/rows/{id}")
    async def api_row_patch(id: str, request: Request) -> dict[str, Any]:
        proj = _require_project()
        body = await _body(request)
        with _state_lock:
            row = next((item for item in proj.rows if item.id == id), None)
            if row is None:
                raise HTTPException(status_code=404, detail=f"unknown row {id!r}")
            if "source" in body:
                new_source = body["source"]
                if not isinstance(new_source, str):
                    raise HTTPException(
                        status_code=400, detail="source must be a string"
                    )
                if new_source != row.source:
                    row.source = new_source
                    for variant in row.variants:
                        projects.set_variant_status(
                            proj, row.id, variant.id, "stale"
                        )
            if "variants" in body:
                edits = body["variants"]
                if isinstance(edits, dict):
                    items: Any = list(edits.items())
                elif isinstance(edits, list):
                    items = []
                    for entry in edits:
                        if (
                            not isinstance(entry, dict)
                            or "id" not in entry
                            or "text" not in entry
                        ):
                            raise HTTPException(
                                status_code=400,
                                detail="variants entries need {id, text}",
                            )
                        items.append((entry["id"], entry["text"]))
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="variants must be a list or an object",
                    )
                for variant_id, text in items:
                    try:
                        projects.update_variant_text(
                            proj,
                            row.id,
                            variant_id,
                            text if isinstance(text, str) else str(text),
                        )
                    except ValueError as exc:
                        raise HTTPException(
                            status_code=404, detail=str(exc)
                        ) from exc
            projects.save_project(proj)
            return _row_to_dict(row)

    @app.post("/api/rows")
    async def api_row_insert(request: Request) -> dict[str, Any]:
        proj = _require_project()
        body = await _body(request)
        source = body.get("source", "")
        translation = body.get("translation")
        if not isinstance(source, str) or not source:
            raise HTTPException(status_code=400, detail="source is required")
        if translation is not None and not isinstance(translation, str):
            raise HTTPException(
                status_code=400, detail="translation must be a string"
            )
        with _state_lock:
            after_row_id = body.get("after_row_id")
            position: int | None
            if after_row_id is not None:
                ref = next((item for item in proj.rows if item.id == after_row_id), None)
                if ref is None:
                    raise HTTPException(
                        status_code=404, detail=f"unknown row {after_row_id!r}"
                    )
                position = ref.position + 1
            elif body.get("position") is not None:
                try:
                    position = int(body["position"])
                except (TypeError, ValueError) as exc:
                    raise HTTPException(
                        status_code=400, detail="position must be an integer"
                    ) from exc
            else:
                position = None
            row = projects.insert_row(proj, position, source, translation)
            projects.save_project(proj)
            return _row_to_dict(row)

    @app.delete("/api/rows/{id}")
    def api_row_delete(id: str) -> dict[str, Any]:
        proj = _require_project()
        with _state_lock:
            try:
                projects.delete_row(proj, id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            projects.save_project(proj)
        return {"deleted": id}

    @app.post("/api/rows/{id}/move")
    async def api_row_move(id: str, request: Request) -> dict[str, Any]:
        proj = _require_project()
        body = await _body(request)
        direction = body.get("direction", "")
        if direction not in ("up", "down"):
            raise HTTPException(
                status_code=400, detail='direction must be "up" or "down"'
            )
        with _state_lock:
            try:
                moved = projects.move_row(proj, id, direction)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            projects.save_project(proj)
            row = next(item for item in proj.rows if item.id == id)
            return {"moved": moved, "row": _row_to_dict(row)}

    @app.get("/api/voices")
    def api_voices(
        model: str | None = None, language: str | None = None
    ) -> list[Any]:
        resolved_model = model
        if resolved_model is None:
            resolved_model = (
                current.tts_model if current is not None else _DEFAULT_TTS_MODEL
            )
        voices = tts.list_voices(model=resolved_model, language=language)
        return [_voice_to_dict(voice) for voice in voices]

    @app.post("/api/voice/test")
    async def api_voice_test(request: Request) -> Response:
        body = await _body(request)
        voice = body.get("voice", "")
        text = body.get("text", "")
        model = body.get("model") or (
            current.tts_model if current is not None else _DEFAULT_TTS_MODEL
        )
        if not isinstance(voice, str) or not voice:
            raise HTTPException(status_code=400, detail="voice is required")
        if not isinstance(text, str) or not text:
            raise HTTPException(status_code=400, detail="text is required")
        collect_cost: dict[str, Any] = {}
        data = tts.test_voice(voice, model, text, collect_cost=collect_cost)
        known = bool(collect_cost.get("known"))
        total = round(float(collect_cost.get("usd") or 0.0), 6)
        _record_cost("tts", total if known else 0.0)
        # Bytes contract unchanged: still the WAV; the estimate rides in a
        # header only when usage was reported (frontend toasts "est." then).
        headers = {"X-Est-Cost-USD": str(total)} if known else None
        return Response(
            content=bytes(data), media_type="audio/wav", headers=headers
        )

    @app.post("/api/tts/generate")
    async def api_tts_generate(request: Request) -> dict[str, Any]:
        _require_project()
        body = await _body(request)
        variant_ids = body.get("variant_ids")
        if variant_ids is not None and (
            not isinstance(variant_ids, list)
            or not all(isinstance(item, str) for item in variant_ids)
        ):
            raise HTTPException(
                status_code=400, detail="variant_ids must be a list of variant ids"
            )
        force = bool(body.get("force", False))
        wanted: list[str] | None = (
            list(variant_ids) if variant_ids is not None else None
        )
        job_id = _start_job_or_409(
            "tts", lambda job: _tts_run(wanted, force, job)
        )
        return {"job_id": job_id}

    @app.post("/api/track/build")
    async def api_track_build(request: Request) -> dict[str, Any]:
        _require_project()
        body = await _body(request)
        wanted: list[tuple[str, str]] | None = None
        if "included" in body and body["included"] is not None:
            raw = body["included"]
            if not isinstance(raw, list) or not all(
                isinstance(item, str) and ":" in item for item in raw
            ):
                raise HTTPException(
                    status_code=400,
                    detail='included must be a list of "row_id:variant_id" strings',
                )
            wanted = [
                (item.split(":", 1)[0], item.split(":", 1)[1]) for item in raw
            ]
        job_id = _start_job_or_409("track", lambda job: _track_run(job, wanted))
        return {"job_id": job_id}

    @app.get("/api/track/estimate")
    def api_track_estimate(included: str | None = None) -> dict[str, Any]:
        proj = _require_project()
        pairs: list[tuple[str, str]]
        if included is None:
            pairs = [
                (row.id, variant.id)
                for row in proj.rows
                for variant in row.variants
                if variant.status == "ok"
            ]
        else:
            pairs = []
            for item in included.split(","):
                item = item.strip()
                if not item:
                    continue
                if ":" not in item:
                    raise HTTPException(
                        status_code=400,
                        detail='included must be "row_id:variant_id" entries',
                    )
                row_id, _, variant_id = item.partition(":")
                pairs.append((row_id, variant_id))
        try:
            duration = float(
                assembler.estimate_duration(
                    proj,
                    pairs,
                    repeats=proj.repeats,
                    repeat_gap_s=proj.repeat_gap_s,
                    item_gap_s=proj.item_gap_s,
                )
            )
        except Exception:
            duration = None
        return {"duration_s": duration}

    @app.patch("/api/project/settings")
    async def api_project_settings(request: Request) -> dict[str, Any]:
        proj = _require_project()
        body = await _body(request)
        allowed = {"repeats", "repeat_gap_s", "item_gap_s", "voice", "tts_model"}
        unknown = sorted(key for key in body if key not in allowed)
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"unknown settings: {unknown}",
            )
        with _state_lock:
            if "repeats" in body:
                try:
                    repeats = int(body["repeats"])
                except (TypeError, ValueError) as exc:
                    raise HTTPException(
                        status_code=400, detail="repeats must be an integer"
                    ) from exc
                if not 1 <= repeats <= 10:
                    raise HTTPException(
                        status_code=400,
                        detail="repeats must be between 1 and 10",
                    )
                proj.repeats = repeats
            for key in ("repeat_gap_s", "item_gap_s"):
                if key in body:
                    try:
                        value = float(body[key])
                    except (TypeError, ValueError) as exc:
                        raise HTTPException(
                            status_code=400, detail=f"{key} must be a number"
                        ) from exc
                    if not 0 <= value <= 60:
                        raise HTTPException(
                            status_code=400,
                            detail=f"{key} must be between 0 and 60",
                        )
                    setattr(proj, key, value)
            if "voice" in body:
                voice = body["voice"]
                if not isinstance(voice, str) or not voice:
                    raise HTTPException(
                        status_code=400, detail="voice must be a non-empty string"
                    )
                proj.voice = voice
            if "tts_model" in body:
                model = body["tts_model"]
                if not isinstance(model, str) or not model:
                    raise HTTPException(
                        status_code=400,
                        detail="tts_model must be a non-empty string",
                    )
                proj.tts_model = model
            projects.save_project(proj)
            return _project_meta(proj)

    @app.get("/api/settings")
    def api_settings() -> dict[str, Any]:
        return _settings_payload()

    @app.patch("/api/settings")
    async def api_settings_patch(request: Request) -> dict[str, Any]:
        body = await _body(request)
        allowed = {"gemini_api_key", "export_root"}
        unknown = sorted(key for key in body if key not in allowed)
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"unknown settings: {unknown}",
            )
        patch: dict[str, Any] = {}
        if "gemini_api_key" in body:
            raw = body["gemini_api_key"]
            if raw is None:
                patch["gemini_api_key"] = None
            elif not isinstance(raw, str):
                raise HTTPException(
                    status_code=400, detail="gemini_api_key must be a string"
                )
            else:
                value = raw.strip()
                if raw == "":
                    patch["gemini_api_key"] = None
                elif not value:
                    raise HTTPException(
                        status_code=400,
                        detail="gemini_api_key must not be whitespace",
                    )
                elif len(value) < 8:
                    raise HTTPException(
                        status_code=400,
                        detail="gemini_api_key must be at least 8 characters",
                    )
                else:
                    patch["gemini_api_key"] = value
        if "export_root" in body:
            raw = body["export_root"]
            if raw is None:
                patch["export_root"] = None
            elif not isinstance(raw, str):
                raise HTTPException(
                    status_code=400, detail="export_root must be a string"
                )
            else:
                value = raw.strip()
                if not value:
                    patch["export_root"] = None
                else:
                    root = Path(value).expanduser()
                    if not root.is_absolute():
                        raise HTTPException(
                            status_code=400,
                            detail="output folder must be an absolute path",
                        )
                    try:
                        root.mkdir(parents=True, exist_ok=True)
                    except OSError as exc:
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                f"cannot use output folder {root}: "
                                f"{exc.strerror or exc}"
                            ),
                        ) from exc
                    patch["export_root"] = str(root)
        old_key = settings_store.load().get("gemini_api_key")
        if "gemini_api_key" in patch and patch["gemini_api_key"] is None:
            config.restore_env_key(old_key)
        try:
            settings_store.save(patch)
        except OSError as exc:
            raise HTTPException(
                status_code=500, detail=f"could not save settings: {exc}"
            ) from exc
        if "gemini_api_key" in patch:
            try:
                config.apply_api_key_to_env()
            except RuntimeError:
                pass  # no key from any source; GET reports has_key=false
        return _settings_payload()

    @app.get("/api/costs")
    def api_costs() -> dict[str, Any]:
        """Local cost-estimate ledger summary (spec F12) — no keys, ever.

        Payload is :func:`app.cost_ledger.summary` served as-is:
        ``{current_month, current:{translate_usd, tts_usd, total_usd,
        calls}, history:[...], pricing_version, note}``.
        """
        return cost_ledger.summary()

    @app.post("/api/system/reveal")
    async def api_system_reveal(request: Request) -> dict[str, Any]:
        proj = _require_project()
        body = await _body(request)
        target = body.get("target")
        root = config.export_dir(proj.folder.name).resolve()
        if target == "folder":
            path = root
        elif target in ("mp3", "wav"):
            path = root / f"final.{target}"
        elif isinstance(target, str) and target:
            # Unknown target: only ever accepted inside the export dir
            # (traversal such as "../../etc/passwd" must 404).
            path = (root / target).resolve()
        else:
            raise HTTPException(status_code=404, detail="not found")
        if not path.resolve().is_relative_to(root) or not path.exists():
            raise HTTPException(status_code=404, detail="not found")
        opened, selected = _launch_reveal(path)
        if not opened:
            raise HTTPException(
                status_code=501,
                detail="no file manager available (tried nautilus, nemo, xdg-open)",
            )
        return {"opened": opened, "selected": selected}

    @app.get("/api/track")
    def api_track() -> dict[str, Any]:
        proj = _require_project()
        return _track_info(proj)

    @app.get("/api/jobs/{id}")
    def api_job_get(id: str) -> dict[str, Any]:
        job = jobs.get_job(id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"unknown job {id!r}")
        return dict(job.to_dict())

    @app.post("/api/jobs/{id}/cancel")
    def api_job_cancel(id: str) -> dict[str, Any]:
        if not jobs.cancel_job(id):
            raise HTTPException(status_code=404, detail=f"unknown job {id!r}")
        return {"cancelled": True}

    @app.get("/export/{path:path}")
    def api_export(path: str) -> FileResponse:
        proj = _require_project()
        root = config.export_dir(proj.folder.name).resolve()
        target = (root / path).resolve()
        if not target.is_relative_to(root):
            raise HTTPException(status_code=404, detail="not found")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(str(target))

    @app.get("/media/{path:path}")
    def api_media(path: str) -> FileResponse:
        proj = _require_project()
        root = proj.folder.resolve()
        target = (proj.folder / path).resolve()
        if not target.is_relative_to(root):
            raise HTTPException(status_code=404, detail="not found")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(str(target))

    frontend_dir = Path(__file__).resolve().parent / "frontend"
    index_file = frontend_dir / "index.html"
    if frontend_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    if index_file.is_file():

        @app.get("/")
        def api_index() -> FileResponse:
            return FileResponse(str(index_file))

    else:

        @app.get("/")
        def api_index() -> dict[str, str]:
            return {"app": config.APP_NAME, "status": "no frontend yet"}

    return app


app = create_app()
