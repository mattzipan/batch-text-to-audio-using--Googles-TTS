"""Local cost *estimates* for Gemini API usage (pure, credential-free).

The Gemini API reports token counts (``usage_metadata``), never dollars.
This module multiplies those counts by a Standard-tier pricing table
(https://ai.google.dev/gemini-api/docs/pricing; TTS GA 2026-09-22,
introductory rates through 2026-12-31, doubling 2027-01-01) to produce
rough estimates. Every rendered estimate must be labeled ``est.`` —
never "final"/"charged". Authoritative spend lives in AI Studio Billing.

All readers are defensive (``getattr``); ``usage=None`` (or an unknown
model) returns ``None`` so callers can omit the suffix instead of
rendering ``$0.00`` for unknown cost. Nothing here ever calls ``.text``
on a TTS response.
"""

from __future__ import annotations

from datetime import date
from typing import Any

PRICING_VERSION = "2026-09-22+intro"

# Rates are USD per 1M tokens, Standard tier, introductory (pre-2027) where
# doubles_on is set. cached_in_per_1m only applies to the text model.
PRICING: dict[str, dict[str, Any]] = {
    "gemini-3.8-flash-lite-tts": {
        "input_per_1m": 0.50,
        "audio_per_1m": 6.00,
        "text_out_per_1m": 0.0,
        "cached_in_per_1m": 0.0,
        "effective_from": "2026-09-22",
        "doubles_on": "2027-01-01",
    },
    "gemini-3.8-flash-tts": {
        "input_per_1m": 0.50,
        "audio_per_1m": 9.00,
        "text_out_per_1m": 0.0,
        "cached_in_per_1m": 0.0,
        "effective_from": "2026-09-22",
        "doubles_on": "2027-01-01",
    },
    "gemini-3.5-flash-lite": {
        "input_per_1m": 0.30,
        "audio_per_1m": 0.0,
        "text_out_per_1m": 2.50,
        "cached_in_per_1m": 0.03,
        "effective_from": "2026-09-22",
        "doubles_on": None,  # text pricing is standard, not introductory
    },
}

TRANSLATION_MODEL = "gemini-3.5-flash-lite"

_MILLION = 1_000_000.0


def _as_number(value: Any) -> float:
    """Coerce a token count to float; non-numeric (or bool) values count as 0."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


def _rate_for(model: str, on: date | None = None) -> dict[str, float] | None:
    """Rates in USD/1M for ``model`` on date ``on`` (default: today, local).

    Doubles every rate on/after the entry's ``doubles_on`` date (2027-01-01
    for TTS intro pricing). Returns ``None`` for unknown models.
    """
    entry = PRICING.get(model)
    if entry is None:
        return None
    when = on if on is not None else date.today()
    rates = {
        "input_per_1m": _as_number(entry.get("input_per_1m")),
        "audio_per_1m": _as_number(entry.get("audio_per_1m")),
        "text_out_per_1m": _as_number(entry.get("text_out_per_1m")),
        "cached_in_per_1m": _as_number(entry.get("cached_in_per_1m")),
    }
    doubles_on = entry.get("doubles_on")
    if doubles_on:
        try:
            flip = date.fromisoformat(doubles_on)
        except ValueError:
            flip = None
        if flip is not None and when >= flip:
            rates = {key: value * 2.0 for key, value in rates.items()}
    return rates


def _modality_name(value: Any) -> str:
    """Enum-or-string modality → upper-case name (e.g. "AUDIO", "TEXT")."""
    return str(getattr(value, "name", value) or "").upper()


def _detail_token_count(details: Any, modality: str) -> float | None:
    """Sum token_count over ``prompt/candidates_tokens_details`` entries.

    Returns ``None`` when details are absent/empty (caller falls back to the
    flat token count) or when no entry matches ``modality``.
    """
    if not details:
        return None
    total = 0.0
    matched = False
    for item in details:
        if _modality_name(getattr(item, "modality", None)) == modality:
            total += _as_number(getattr(item, "token_count", 0))
            matched = True
    return total if matched else None


def estimate_translate(usage: Any) -> float | None:
    """Estimate USD for one translation (text) call from its usage_metadata.

    prompt × text-in + candidates × text-out + cached × cached-in, using the
    ``gemini-3.5-flash-lite`` Standard-tier rates. Returns ``None`` when
    ``usage`` is None (or an unknown-model situation) so callers omit the
    suffix rather than show ``$0.00`` for unknown cost.
    """
    if usage is None:
        return None
    rates = _rate_for(TRANSLATION_MODEL)
    if rates is None:  # pragma: no cover - table and constant are kept in sync
        return None
    prompt = _as_number(getattr(usage, "prompt_token_count", 0) or 0)
    candidates = _as_number(getattr(usage, "candidates_token_count", 0) or 0)
    cached = _as_number(getattr(usage, "cached_content_token_count", 0) or 0)
    usd = (
        prompt * rates["input_per_1m"]
        + candidates * rates["text_out_per_1m"]
        + cached * rates["cached_in_per_1m"]
    ) / _MILLION
    return usd


def estimate_tts(usage: Any, model: str) -> float | None:
    """Estimate USD for one TTS call from its usage_metadata.

    prompt-TEXT × text-in + candidates-AUDIO × audio-out for ``model``.
    When per-modality ``*_tokens_details`` are absent, all prompt tokens are
    treated as TEXT and all candidates tokens as AUDIO. Returns ``None`` for
    ``usage=None`` or an unknown model.
    """
    if usage is None:
        return None
    rates = _rate_for(model)
    if rates is None:
        return None
    prompt = _as_number(getattr(usage, "prompt_token_count", 0) or 0)
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    prompt_text = _detail_token_count(prompt_details, "TEXT")
    if prompt_text is None:
        prompt_text = prompt
    candidates = _as_number(getattr(usage, "candidates_token_count", 0) or 0)
    cand_details = getattr(usage, "candidates_tokens_details", None)
    cand_audio = _detail_token_count(cand_details, "AUDIO")
    if cand_audio is None:
        cand_audio = candidates
    usd = (
        prompt_text * rates["input_per_1m"]
        + cand_audio * rates["audio_per_1m"]
    ) / _MILLION
    return usd


def fmt_est(usd: float) -> str:
    """Format an estimate for toasts: ``~$0.0040`` under $0.01, else ``~$0.42``.

    Always keeps the ``~$`` prefix — these are estimates, never final cost.
    """
    if usd < 0.01:
        return f"~${usd:.4f}"
    return f"~${usd:.2f}"
