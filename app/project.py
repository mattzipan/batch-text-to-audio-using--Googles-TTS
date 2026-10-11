"""WordTape project model: ``project.json`` load/save plus row operations.

Storage layout inside a project folder::

    <folder>/project.json          versioned JSON document (see below)
    <folder>/audio/                per-variant WAV cache

``project.json`` shape (version 1)::

    {
      "version": 1,
      "source_lang": "de", "target_lang": "id",
      "variants_enabled": false,
      "tts_model": "gemini-3.8-flash-lite-tts", "voice": "Kore",
      "repeats": 5, "repeat_gap_s": 1.2, "item_gap_s": 1.8,
      "rows": [
        {"id": "a1b2c3", "position": 1, "source": "Guten Morgen",
         "variants": [{"id": "d4e5f6", "style": "main", "text": "Selamat pagi",
                       "audio": "audio/a1b2c3_d4e5f6.wav", "status": "ok"}]}
      ]
    }

Decisions (documented per task A2):

- ``Project.folder`` is **excluded** from ``project.json``: the folder is implied
  by the file's location, so persisting it would be redundant and would break
  when a project directory is moved or renamed. ``load_project`` sets it from
  its ``folder`` argument; :func:`save_project` uses it as the write target.
- Row/variant ids are random 6-char hex (``secrets.token_hex(3)``), unique
  within the project (regenerated on collision), and **never** derived from the
  display position, so insert/delete/reorder cannot break audio cache names.
- ``position`` is the 1-based display order. It is renumbered ``1..N`` in list
  order after every mutation; file names are never renumbered (ids are stable).
- "Insert at row N" means insert **before** the current row N (1-based).
  Out-of-range positions are clamped (``< 1`` becomes front, ``> N+1`` or
  ``None`` appends) instead of raising, so UI number inputs cannot crash.
- ``insert_row`` creates a single ``main`` variant; ``formal``/``informal``
  variants are added later by the translation step when ``variants_enabled``.
- ``delete_row`` removes the row's canonical cached WAVs (see :func:`audio_path`)
  when present and ignores missing files.
- ``save_project`` creates ``folder/`` and ``audio/`` as needed (built tracks live in the export dir)
  and writes atomically (``project.json.tmp`` + ``os.replace``).
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_FILENAME = "project.json"
PROJECT_VERSION = 1

DEFAULT_TTS_MODEL = "gemini-3.8-flash-lite-tts"
DEFAULT_VOICE = "Kore"
DEFAULT_REPEATS = 5
DEFAULT_REPEAT_GAP_S = 1.2
DEFAULT_ITEM_GAP_S = 1.8

VARIANT_STATUSES = ("pending", "generating", "ok", "stale", "error")
VARIANT_STYLES = ("main", "formal", "informal")


@dataclass
class Variant:
    id: str
    style: str = "main"
    text: str = ""
    audio: str = ""
    status: str = "pending"


@dataclass
class Row:
    id: str
    position: int = 0
    source: str = ""
    variants: list[Variant] = field(default_factory=list)


@dataclass
class Project:
    version: int = PROJECT_VERSION
    source_lang: str = "de"
    target_lang: str = "id"
    variants_enabled: bool = False
    tts_model: str = DEFAULT_TTS_MODEL
    voice: str = DEFAULT_VOICE
    repeats: int = DEFAULT_REPEATS
    repeat_gap_s: float = DEFAULT_REPEAT_GAP_S
    item_gap_s: float = DEFAULT_ITEM_GAP_S
    rows: list[Row] = field(default_factory=list)
    folder: Path = field(default_factory=Path)


def _collect_ids(project: Project) -> set[str]:
    ids: set[str] = set()
    for row in project.rows:
        ids.add(row.id)
        for variant in row.variants:
            ids.add(variant.id)
    return ids


def _fresh_id(taken: set[str]) -> str:
    """Return a new 6-hex-char id not in ``taken`` (added to ``taken``)."""
    while True:
        candidate = secrets.token_hex(3)
        if candidate not in taken:
            taken.add(candidate)
            return candidate


def ensure_unique_ids(project: Project) -> Project:
    """Regenerate any duplicated row/variant id (safety net used on load)."""
    seen: set[str] = set()
    for row in project.rows:
        if row.id in seen:
            row.id = _fresh_id(seen)
        else:
            seen.add(row.id)
        for variant in row.variants:
            if variant.id in seen:
                variant.id = _fresh_id(seen)
                variant.audio = f"audio/{row.id}_{variant.id}.wav"
            else:
                seen.add(variant.id)
            # Keep the cached-audio name consistent with stable ids.
            if not variant.audio:
                variant.audio = f"audio/{row.id}_{variant.id}.wav"
        if row.id not in seen:
            seen.add(row.id)
    return project


def _renumber(project: Project) -> None:
    for index, row in enumerate(project.rows, start=1):
        row.position = index


def _find_row(project: Project, row_id: str) -> tuple[int, Row]:
    for index, row in enumerate(project.rows):
        if row.id == row_id:
            return index, row
    raise ValueError(f"unknown row id: {row_id!r}")


def _find_variant(row: Row, variant_id: str) -> Variant:
    for variant in row.variants:
        if variant.id == variant_id:
            return variant
    raise ValueError(f"unknown variant id: {variant_id!r} in row {row.id!r}")


def new_project(
    folder: str | Path,
    source_lang: str,
    target_lang: str,
    variants_enabled: bool,
    *,
    tts_model: str = DEFAULT_TTS_MODEL,
    voice: str = DEFAULT_VOICE,
    repeats: int = DEFAULT_REPEATS,
    repeat_gap_s: float = DEFAULT_REPEAT_GAP_S,
    item_gap_s: float = DEFAULT_ITEM_GAP_S,
) -> Project:
    """Build a new empty project (pure constructor: no disk writes)."""
    return Project(
        version=PROJECT_VERSION,
        source_lang=source_lang,
        target_lang=target_lang,
        variants_enabled=variants_enabled,
        tts_model=tts_model,
        voice=voice,
        repeats=repeats,
        repeat_gap_s=repeat_gap_s,
        item_gap_s=item_gap_s,
        rows=[],
        folder=Path(folder),
    )


def _project_to_dict(project: Project) -> dict:
    return {
        "version": project.version,
        "source_lang": project.source_lang,
        "target_lang": project.target_lang,
        "variants_enabled": project.variants_enabled,
        "tts_model": project.tts_model,
        "voice": project.voice,
        "repeats": project.repeats,
        "repeat_gap_s": project.repeat_gap_s,
        "item_gap_s": project.item_gap_s,
        "rows": [
            {
                "id": row.id,
                "position": row.position,
                "source": row.source,
                "variants": [
                    {
                        "id": variant.id,
                        "style": variant.style,
                        "text": variant.text,
                        "audio": variant.audio,
                        "status": variant.status,
                    }
                    for variant in row.variants
                ],
            }
            for row in project.rows
        ],
    }


def save_project(project: Project) -> Path:
    """Persist ``project.json`` atomically; create folder/audio dirs."""
    project.folder.mkdir(parents=True, exist_ok=True)
    (project.folder / "audio").mkdir(exist_ok=True)
    target = project.folder / PROJECT_FILENAME
    tmp = project.folder / (PROJECT_FILENAME + ".tmp")
    tmp.write_text(
        json.dumps(_project_to_dict(project), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, target)
    return target


def load_project(folder: str | Path) -> Project:
    """Read ``project.json`` from ``folder`` ( Repairs duplicate ids)."""
    folder = Path(folder)
    raw = json.loads((folder / PROJECT_FILENAME).read_text(encoding="utf-8"))
    rows = [
        Row(
            id=row["id"],
            position=int(row.get("position", 0)),
            source=row.get("source", ""),
            variants=[
                Variant(
                    id=variant["id"],
                    style=variant.get("style", "main"),
                    text=variant.get("text", ""),
                    audio=variant.get("audio", ""),
                    status=variant.get("status", "pending"),
                )
                for variant in row.get("variants", [])
            ],
        )
        for row in raw.get("rows", [])
    ]
    project = Project(
        version=int(raw.get("version", PROJECT_VERSION)),
        source_lang=raw.get("source_lang", "de"),
        target_lang=raw.get("target_lang", "id"),
        variants_enabled=bool(raw.get("variants_enabled", False)),
        tts_model=raw.get("tts_model", DEFAULT_TTS_MODEL),
        voice=raw.get("voice", DEFAULT_VOICE),
        repeats=int(raw.get("repeats", DEFAULT_REPEATS)),
        repeat_gap_s=float(raw.get("repeat_gap_s", DEFAULT_REPEAT_GAP_S)),
        item_gap_s=float(raw.get("item_gap_s", DEFAULT_ITEM_GAP_S)),
        rows=rows,
        folder=folder,
    )
    ensure_unique_ids(project)
    _renumber(project)
    return project


def insert_row(
    project: Project,
    position: int | None,
    source: str,
    translation: str | None = None,
) -> Row:
    """Insert a row with one ``main`` variant.

    ``position`` is the 1-based display position to insert **before**;
    ``None`` (or past-the-end) appends. Positions are renumbered ``1..N``.
    """
    taken = _collect_ids(project)
    row_id = _fresh_id(taken)
    variant_id = _fresh_id(taken)
    row = Row(
        id=row_id,
        position=0,
        source=source,
        variants=[
            Variant(
                id=variant_id,
                style="main",
                text=translation if translation is not None else "",
                audio=f"audio/{row_id}_{variant_id}.wav",
                status="pending",
            )
        ],
    )
    if position is None:
        project.rows.append(row)
    else:
        index = max(0, min(int(position) - 1, len(project.rows)))
        project.rows.insert(index, row)
    _renumber(project)
    return row


def delete_row(project: Project, row_id: str) -> Row:
    """Delete a row, its cached audio files, and renumber ``1..N``."""
    index, row = _find_row(project, row_id)
    for variant in row.variants:
        audio_path(project, row.id, variant.id).unlink(missing_ok=True)
    del project.rows[index]
    _renumber(project)
    return row


def move_row(project: Project, row_id: str, direction: str) -> bool:
    """Move a row ``"up"``/``"down"`` one step; no-op (``False``) at boundaries."""
    if direction not in ("up", "down"):
        raise ValueError(f"direction must be 'up' or 'down', got {direction!r}")
    index, row = _find_row(project, row_id)
    other = index - 1 if direction == "up" else index + 1
    if other < 0 or other >= len(project.rows):
        return False
    project.rows[index], project.rows[other] = project.rows[other], project.rows[index]
    _renumber(project)
    return True


def update_variant_text(
    project: Project, row_id: str, variant_id: str, text: str
) -> Variant:
    """Replace variant text; marks the variant ``"stale"`` (needs regeneration)."""
    _, row = _find_row(project, row_id)
    variant = _find_variant(row, variant_id)
    variant.text = text
    variant.status = "stale"
    return variant


def set_variant_status(
    project: Project, row_id: str, variant_id: str, status: str
) -> Variant:
    """Set a variant status (one of ``pending|generating|ok|stale|error``)."""
    if status not in VARIANT_STATUSES:
        raise ValueError(f"invalid status {status!r}; expected one of {VARIANT_STATUSES}")
    _, row = _find_row(project, row_id)
    variant = _find_variant(row, variant_id)
    variant.status = status
    return variant


def audio_path(project: Project, row_id: str, variant_id: str) -> Path:
    """Canonical cache path: ``<folder>/audio/<row_id>_<variant_id>.wav``."""
    return project.folder / "audio" / f"{row_id}_{variant_id}.wav"
