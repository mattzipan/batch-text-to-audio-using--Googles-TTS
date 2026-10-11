"""Local monthly cost-estimate ledger (JSON under XDG_DATA_HOME).

Accumulates the *estimates* produced by :mod:`app.costs` per calendar month
(``%Y-%m``, server local time) at ``$XDG_DATA_HOME/WordTape/costs.json``
(default ``~/.local/share/WordTape/costs.json``). This is a local
accumulator, not an invoice — the Gemini API is pay-as-you-go/prepay and
has no month-end charge. Never stores the API key.

The server (not this module) owns HTTP: it calls :func:`record` after each
successful billable completion and serves :func:`summary` from
``GET /api/costs``.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

PRICING_VERSION = "2026-09-22+intro"

NOTE = (
    "Estimates from usageMetadata × Standard-tier table. "
    "Authoritative spend: AI Studio Billing."
)

_KIND_TO_FIELD = {"translate": "translate_usd", "tts": "tts_usd"}

# Serializes load→mutate→write; concurrent jobs may record at the same time.
_LOCK = threading.Lock()


def ledger_path() -> Path:
    """``$XDG_DATA_HOME/WordTape/costs.json``, else ``~/.local/share/...``."""
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "WordTape" / "costs.json"


def _empty_ledger() -> dict[str, Any]:
    return {"months": {}, "pricing_version": PRICING_VERSION}


def load() -> dict[str, Any]:
    """Return the ledger dict; missing or corrupt file yields an empty ledger."""
    try:
        raw = json.loads(ledger_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _empty_ledger()
    months = raw.get("months") if isinstance(raw, dict) else None
    if not isinstance(months, dict):
        months = {}
    version = raw.get("pricing_version") if isinstance(raw, dict) else None
    return {"months": months, "pricing_version": version or PRICING_VERSION}


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp, path)


def record(kind: str, usd: float) -> None:
    """Add ``usd`` to the current local-time month bucket for ``kind``.

    ``kind`` is ``"translate"`` or ``"tts"``. Rounds to 6 decimals, creates
    the ``%Y-%m`` bucket if needed, increments ``calls`` by 1, stamps
    ``updated_at``, and writes atomically (tmp + ``os.replace``) under a
    lock. Best-effort: never raises (callers may also wrap in try/except).
    """
    try:
        with _LOCK:
            field = _KIND_TO_FIELD[kind]
            data = load()
            now = datetime.now()
            month = now.strftime("%Y-%m")
            bucket = data["months"].get(month)
            if not isinstance(bucket, dict):
                bucket = {}
            for key in ("translate_usd", "tts_usd"):
                prev = bucket.get(key)
                if isinstance(prev, bool) or not isinstance(prev, (int, float)):
                    bucket[key] = 0.0
            bucket[field] = round(float(bucket[field]) + float(usd), 6)
            calls = bucket.get("calls")
            if isinstance(calls, bool) or not isinstance(calls, (int, float)):
                calls = 0
            bucket["calls"] = int(calls) + 1
            bucket["updated_at"] = now.isoformat(timespec="seconds")
            data["months"][month] = bucket
            data["pricing_version"] = PRICING_VERSION
            _atomic_write(ledger_path(), data)
    except Exception:  # noqa: BLE001 - ledger is best-effort, never breaks callers
        return


def _month_payload(month: str, bucket: Any) -> dict[str, Any]:
    if not isinstance(bucket, dict):
        bucket = {}

    def num(key: str) -> float:
        value = bucket.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return 0.0
        return round(float(value), 6)

    translate = num("translate_usd")
    tts = num("tts_usd")
    calls = bucket.get("calls")
    if isinstance(calls, bool) or not isinstance(calls, (int, float)):
        calls = 0
    return {
        "month": month,
        "translate_usd": translate,
        "tts_usd": tts,
        "total_usd": round(translate + tts, 6),
        "calls": int(calls),
    }


def summary(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the ``GET /api/costs`` payload from a ledger dict.

    ``data`` defaults to :func:`load`. Returns::

        {"current_month": "2026-10",
         "current": {translate_usd, tts_usd, total_usd, calls},
         "history": [{month, translate_usd, tts_usd, total_usd, calls}, ...]
                    # newest first, current month included (first row)
         "pricing_version": "2026-09-22+intro",
         "note": "Estimates from usageMetadata × Standard-tier table. ..."}

    Pure function — no HTTP code, no file writes. Missing months are zeros.
    """
    if data is None:
        data = load()
    months = data.get("months")
    if not isinstance(months, dict):
        months = {}
    current_month = datetime.now().strftime("%Y-%m")
    history = [
        _month_payload(str(month), months[month])
        for month in sorted(months, reverse=True)
    ]
    current = _month_payload(current_month, months.get(current_month))
    current_payload = {
        "translate_usd": current["translate_usd"],
        "tts_usd": current["tts_usd"],
        "total_usd": current["total_usd"],
        "calls": current["calls"],
    }
    return {
        "current_month": current_month,
        "current": current_payload,
        "history": history,
        "pricing_version": data.get("pricing_version") or PRICING_VERSION,
        "note": NOTE,
    }
