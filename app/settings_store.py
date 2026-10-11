"""Per-machine WordTape settings persisted to settings.json (spec F7/F8).

Location: ``$XDG_DATA_HOME/WordTape/settings.json`` (default
``~/.local/share/WordTape/settings.json``). Directory ``0o700``, file
``0o600``, written atomically (tmp + ``os.replace``).

Schema: ``{gemini_api_key: str|null, export_root: str|null}``. ``None``
means "not set" (key falls back to env/baked, export root to default).
This module never logs or prints values, and reading it at import time
never touches key material (all I/O is inside :func:`load` / :func:`save`).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_KEYS = ("gemini_api_key", "export_root")

_DEFAULTS: dict[str, str | None] = {"gemini_api_key": None, "export_root": None}


def settings_dir() -> Path:
    """Directory holding settings.json (XDG_DATA_HOME-aware)."""
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return base / "WordTape"


def settings_path() -> Path:
    """Full path of settings.json."""
    return settings_dir() / "settings.json"


def load() -> dict[str, Any]:
    """Return the settings dict; defaults when the file is missing/broken."""
    out = dict(_DEFAULTS)
    try:
        raw = settings_path().read_text(encoding="utf-8")
    except OSError:
        return out
    try:
        data = json.loads(raw)
    except ValueError:
        return out
    if not isinstance(data, dict):
        return out
    for key in SCHEMA_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value:
            out[key] = value
    return out


def save(patch: dict[str, Any]) -> dict[str, Any]:
    """Merge ``patch`` into the settings and write atomically.

    Unknown keys are ignored; empty/whitespace values clear the key
    (set to ``None``). Returns the merged settings. Raises OSError if the
    file cannot be written (callers surface that as a 400/500).
    """
    merged = load()
    for key, value in patch.items():
        if key not in SCHEMA_KEYS:
            continue
        merged[key] = value if isinstance(value, str) and value.strip() else None
    _write(merged)
    return merged


def _write(data: dict[str, Any]) -> None:
    directory = settings_dir()
    directory.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    fd, tmp_name = tempfile.mkstemp(prefix="settings.", dir=str(directory))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        try:
            os.chmod(tmp_path, 0o600)
        except OSError:
            pass
        os.replace(tmp_path, directory / "settings.json")
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
