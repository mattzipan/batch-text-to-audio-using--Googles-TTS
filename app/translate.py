"""WordTape translation service: batched glossary translation via Gemini text model.

Uses ``google-genai`` ``client.models.generate_content`` with a JSON response
mime type. Rows are sent in chunks of 25; results map back to rows by chunk
position (never by source-text matching).
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from typing import Any

from google import genai
from google.genai import types

from app import config
from app import costs
from app.project import Row

_BATCH_SIZE = 25
_MAX_ATTEMPTS = 3
_BACKOFF_S = (2.0, 4.0, 8.0)

_RETRY_SUFFIX = "\nReturn ONLY valid JSON, no other text."

_TRANSIENT_CODE_RE = re.compile(r"\b(429|5\d\d)\b")


def _is_auth_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if code is None:
        code = getattr(exc, "status_code", None)
    if code in (401, 403):
        return True
    text = f"{type(exc).__name__}: {exc}".lower()
    if "api key not valid" in text or "unauthenticated" in text:
        return True
    return bool(re.search(r"\b(401|403)\b", text))


def _is_transient(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if code is None:
        code = getattr(exc, "status_code", None)
    if code == 429 or (isinstance(code, int) and 500 <= code < 600):
        return True
    text = f"{type(exc).__name__}: {exc}".lower()
    if _TRANSIENT_CODE_RE.search(text):
        return True
    return (
        "resource_exhausted" in text
        or "unavailable" in text
        or "too many requests" in text
    )


def _build_prompt(
    source_lang: str, target_lang: str, with_variants: bool, chunk: list[Row]
) -> str:
    if with_variants:
        instruction = (
            f"Translate each source term from {source_lang} into {target_lang}. "
            'Return a JSON array of objects with keys "source", "translation", '
            '"formal", "informal". '
            "translation = the most common everyday translation. "
            "formal/informal = alternatives with exactly the same meaning but "
            "more formal/informal register, or null if the language makes no "
            "such distinction. "
            "Never translate names."
        )
    else:
        instruction = (
            f"Translate each source term from {source_lang} into {target_lang}. "
            'Return a JSON array of objects with keys "source" and "translation". '
            "translation = the most common everyday translation. "
            "Never translate names."
        )
    lines = [instruction, "Terms (return one object per term, in the same order):"]
    lines.extend(f"{i}. {row.source}" for i, row in enumerate(chunk, start=1))
    lines.append("Return ONLY the JSON array.")
    return "\n".join(lines)


def _strip_fences(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        newline = s.find("\n")
        if newline != -1:
            s = s[newline + 1 :]
        else:
            s = s[3:]
        stripped = s.rstrip()
        if stripped.endswith("```"):
            stripped = stripped[: -len("```")]
        s = stripped.strip()
    return s


def _extract_entries(response: Any, expected_len: int) -> list[dict[str, Any]]:
    text = getattr(response, "text", None)
    if text is None:
        raise ValueError("empty model response (no text)")
    if not isinstance(text, str):
        text = str(text)
    stripped = _strip_fences(text)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError(f"expected JSON array, got {type(data).__name__}")
    if len(data) != expected_len:
        raise ValueError(f"expected {expected_len} entries, got {len(data)}")
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("array entries must be objects")
    return data


def _call_with_retries(client: Any, contents: str) -> Any:
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return client.models.generate_content(
                model=config.TRANSLATION_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )
        except Exception as exc:  # noqa: BLE001 - classified below
            if _is_auth_error(exc):
                raise RuntimeError(f"Gemini API auth failed: {exc}") from exc
            if _is_transient(exc) and attempt < _MAX_ATTEMPTS:
                time.sleep(_BACKOFF_S[attempt - 1])
                continue
            raise


def _coerce_str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _estimate_response_cost(response: Any) -> float | None:
    """Local cost estimate for one generate_content response; never raises."""
    try:
        return costs.estimate_translate(getattr(response, "usage_metadata", None))
    except Exception:  # noqa: BLE001 - costing must never break translation
        return None


def translate_rows(
    rows: list[Row],
    source_lang: str,
    target_lang: str,
    with_variants: bool,
    client: Any | None = None,
    progress: Callable[[int, int], None] | None = None,
    cancel: Callable[[], bool] | None = None,
    collect_costs: list | None = None,
) -> dict[str, dict[str, str | None]]:
    """Translate ``rows`` in batches of 25 via the Gemini text model.

    Returns a mapping of ``row.id`` to ``{"translation", "formal", "informal"}``.
    ``translation`` coerces missing/null to ``""``; ``formal``/``informal`` stay
    ``None`` when absent (and are always ``None`` when ``with_variants`` is
    False).

    When ``collect_costs`` is given, it receives one local cost estimate
    (USD, from usage_metadata × the pricing table) after each actual
    ``_call_with_retries`` invocation — the first try *and* any
    ``_RETRY_SUFFIX`` parse retry — appended only when the estimate is not
    ``None``. Estimates are approximate; billed cost lives in AI Studio
    Billing.
    """
    if not rows:
        return {}
    if client is None:
        client = genai.Client()

    total = len(rows)
    num_batches = (total + _BATCH_SIZE - 1) // _BATCH_SIZE
    out: dict[str, dict[str, str | None]] = {}
    done = 0

    for batch_idx, start in enumerate(range(0, total, _BATCH_SIZE), start=1):
        if cancel is not None and cancel():
            raise RuntimeError("cancelled")
        chunk = rows[start : start + _BATCH_SIZE]
        contents = _build_prompt(source_lang, target_lang, with_variants, chunk)

        try:
            response = _call_with_retries(client, contents)
        except RuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001 - wrapped as batch error
            raise RuntimeError(
                f"translation batch {batch_idx}/{num_batches} failed: {exc}"
            ) from exc
        if collect_costs is not None:
            estimate = _estimate_response_cost(response)
            if estimate is not None:
                collect_costs.append(estimate)

        try:
            entries = _extract_entries(response, len(chunk))
        except ValueError:
            retry_contents = contents + _RETRY_SUFFIX
            try:
                retry_response = _call_with_retries(client, retry_contents)
            except RuntimeError:
                raise
            except Exception as exc:  # noqa: BLE001 - wrapped as batch error
                raise RuntimeError(
                    f"translation batch {batch_idx}/{num_batches} failed: {exc}"
                ) from exc
            if collect_costs is not None:
                retry_estimate = _estimate_response_cost(retry_response)
                if retry_estimate is not None:
                    collect_costs.append(retry_estimate)
            try:
                entries = _extract_entries(retry_response, len(chunk))
            except ValueError as exc:
                raise RuntimeError(
                    f"translation batch {batch_idx}/{num_batches} "
                    f"failed to parse model output: {exc}"
                ) from exc

        for row, entry in zip(chunk, entries):
            raw_translation = entry.get("translation")
            if raw_translation is None:
                translation = ""
            elif isinstance(raw_translation, str):
                translation = raw_translation
            else:
                translation = str(raw_translation)
            if with_variants:
                formal = _coerce_str_or_none(entry.get("formal"))
                informal = _coerce_str_or_none(entry.get("informal"))
            else:
                formal = None
                informal = None
            out[row.id] = {
                "translation": translation,
                "formal": formal,
                "informal": informal,
            }

        done += len(chunk)
        if progress is not None:
            progress(done, total)

    return out
