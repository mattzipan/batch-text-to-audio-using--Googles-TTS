"""Tests for app.costs: pricing table, rate doubling, estimates, formatting."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import costs


def test_pricing_has_exact_model_ids_from_spec():
    assert set(costs.PRICING) == {
        "gemini-3.8-flash-lite-tts",
        "gemini-3.8-flash-tts",
        "gemini-3.5-flash-lite",
    }
    lite = costs.PRICING["gemini-3.8-flash-lite-tts"]
    assert lite["input_per_1m"] == 0.50
    assert lite["audio_per_1m"] == 6.00
    assert lite["doubles_on"] == "2027-01-01"
    flagship = costs.PRICING["gemini-3.8-flash-tts"]
    assert flagship["input_per_1m"] == 0.50
    assert flagship["audio_per_1m"] == 9.00
    text = costs.PRICING["gemini-3.5-flash-lite"]
    assert text["input_per_1m"] == 0.30
    assert text["text_out_per_1m"] == 2.50
    assert text["cached_in_per_1m"] == 0.03
    for entry in costs.PRICING.values():
        assert entry["effective_from"] == "2026-09-22"


def test_rate_for_intro_rates_before_2027():
    rates = costs._rate_for("gemini-3.8-flash-lite-tts", on=date(2026, 12, 31))
    assert rates["input_per_1m"] == 0.50
    assert rates["audio_per_1m"] == 6.00


def test_rate_for_doubles_on_2027():
    rates = costs._rate_for("gemini-3.8-flash-lite-tts", on=date(2027, 1, 1))
    assert rates["input_per_1m"] == 1.00
    assert rates["audio_per_1m"] == 12.00
    flagship = costs._rate_for("gemini-3.8-flash-tts", on=date(2027, 6, 1))
    assert flagship["input_per_1m"] == 1.00
    assert flagship["audio_per_1m"] == 18.00


def test_rate_for_translation_model_never_doubles():
    before = costs._rate_for("gemini-3.5-flash-lite", on=date(2026, 10, 1))
    after = costs._rate_for("gemini-3.5-flash-lite", on=date(2028, 1, 1))
    assert before == after
    assert before["input_per_1m"] == 0.30
    assert before["text_out_per_1m"] == 2.50


def test_rate_for_unknown_model_is_none():
    assert costs._rate_for("gemini-9.9-nope") is None


def _tts_usage(prompt=29, candidates=92, audio_tokens=None, prompt_details=None):
    if audio_tokens is None:
        audio_tokens = candidates
    return SimpleNamespace(
        prompt_token_count=prompt,
        candidates_token_count=candidates,
        prompt_tokens_details=prompt_details,
        candidates_tokens_details=[
            SimpleNamespace(modality=SimpleNamespace(name="AUDIO"), token_count=audio_tokens)
        ],
    )


def test_estimate_tts_verify_math_from_spec():
    # 29 prompt tokens × $0.50/1M + 92 audio candidates × $6.00/1M.
    usage = _tts_usage()
    est = costs.estimate_tts(usage, "gemini-3.8-flash-lite-tts")
    assert est == pytest.approx(29 / 1e6 * 0.50 + 92 / 1e6 * 6.00)
    assert est == pytest.approx(0.0005665)


def test_estimate_tts_flagship_uses_9_dollar_audio_rate():
    usage = _tts_usage()
    est = costs.estimate_tts(usage, "gemini-3.8-flash-tts")
    assert est == pytest.approx(29 / 1e6 * 0.50 + 92 / 1e6 * 9.00)


def test_estimate_tts_without_details_treats_all_candidates_as_audio():
    usage = SimpleNamespace(
        prompt_token_count=29,
        candidates_token_count=92,
        prompt_tokens_details=None,
        candidates_tokens_details=None,
    )
    est = costs.estimate_tts(usage, "gemini-3.8-flash-lite-tts")
    assert est == pytest.approx(29 / 1e6 * 0.50 + 92 / 1e6 * 6.00)


def test_estimate_tts_prompt_details_exclude_audio_prompt_tokens():
    prompt_details = [
        SimpleNamespace(modality=SimpleNamespace(name="TEXT"), token_count=20),
        SimpleNamespace(modality=SimpleNamespace(name="AUDIO"), token_count=9),
    ]
    usage = _tts_usage(prompt_details=prompt_details)
    est = costs.estimate_tts(usage, "gemini-3.8-flash-lite-tts")
    # only the 20 TEXT prompt tokens are billed at text-in rate
    assert est == pytest.approx(20 / 1e6 * 0.50 + 92 / 1e6 * 6.00)


def test_estimate_tts_modality_as_plain_string():
    usage = SimpleNamespace(
        prompt_token_count=10,
        candidates_token_count=25,
        candidates_tokens_details=[
            SimpleNamespace(modality="AUDIO", token_count=25)
        ],
    )
    est = costs.estimate_tts(usage, "gemini-3.8-flash-lite-tts")
    assert est == pytest.approx(10 / 1e6 * 0.50 + 25 / 1e6 * 6.00)


def test_estimate_tts_usage_none_is_none():
    assert costs.estimate_tts(None, "gemini-3.8-flash-lite-tts") is None


def test_estimate_tts_unknown_model_is_none():
    assert costs.estimate_tts(_tts_usage(), "gemini-9.9-nope") is None


def test_estimate_tts_missing_counts_are_zero_not_none():
    usage = SimpleNamespace()  # present but empty — $0.00 is a real estimate
    est = costs.estimate_tts(usage, "gemini-3.8-flash-lite-tts")
    assert est == pytest.approx(0.0)


def test_estimate_translate_verify_math_from_spec():
    usage = SimpleNamespace(prompt_token_count=1000, candidates_token_count=400)
    est = costs.estimate_translate(usage)
    assert est == pytest.approx(1000 / 1e6 * 0.30 + 400 / 1e6 * 2.50)
    assert est == pytest.approx(0.0013)


def test_estimate_translate_cached_tokens_only_when_positive():
    usage = SimpleNamespace(
        prompt_token_count=1000, candidates_token_count=400, cached_content_token_count=0
    )
    base = costs.estimate_translate(usage)
    usage2 = SimpleNamespace(
        prompt_token_count=1000,
        candidates_token_count=400,
        cached_content_token_count=200,
    )
    with_cache = costs.estimate_translate(usage2)
    assert base == pytest.approx(1000 / 1e6 * 0.30 + 400 / 1e6 * 2.50)
    assert with_cache == pytest.approx(base + 200 / 1e6 * 0.03)


def test_estimate_translate_usage_none_is_none():
    assert costs.estimate_translate(None) is None


def test_estimate_translate_is_defensive_against_garbage():
    # MagicMock attributes are non-numeric: coerced to 0, never raises.
    est = costs.estimate_translate(MagicMock())
    assert isinstance(est, float)
    assert costs.estimate_translate(SimpleNamespace()) == pytest.approx(0.0)


def test_fmt_est_four_decimals_under_one_cent():
    assert costs.fmt_est(0.004) == "~$0.0040"
    assert costs.fmt_est(0.0004) == "~$0.0004"
    assert costs.fmt_est(0.0099) == "~$0.0099"


def test_fmt_est_two_decimals_at_one_cent_and_up():
    assert costs.fmt_est(0.01) == "~$0.01"
    assert costs.fmt_est(0.021) == "~$0.02"
    assert costs.fmt_est(1.5) == "~$1.50"
    assert costs.fmt_est(0.0) == "~$0.0000"  # only when caller knows it is zero


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
