"""Gemini backend tests: request shape, WAV passthrough, error mapping (mocked)."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backends.base import SynthesisRequest  # noqa: E402
from backends.gemini import DEFAULT_MODEL, GeminiBackend  # noqa: E402


def _ok_response(audio: bytes = b"RIFF-test"):
    part = SimpleNamespace(inline_data=SimpleNamespace(data=audio))
    return SimpleNamespace(parts=[part], prompt_feedback=None)


def _mock_client(audio: bytes = b"RIFF-test"):
    client = MagicMock()
    client.models.generate_content.return_value = _ok_response(audio)
    return client


def test_request_construction_default_voice():
    client = _mock_client()
    backend = GeminiBackend(client=client)
    audio, usage = backend._synthesize_one(SynthesisRequest(text="Halo!"))
    assert audio == b"RIFF-test"
    assert usage is None  # mock response carries no usage_metadata
    _, kwargs = client.models.generate_content.call_args
    assert kwargs["model"] == DEFAULT_MODEL
    assert kwargs["config"].response_modalities == ["AUDIO"]
    voice_cfg = kwargs["config"].speech_config.voice_config
    assert voice_cfg.prebuilt_voice_config.voice_name == "Kore"
    contents = kwargs["contents"]
    assert contents[0]["parts"][0]["text"] == "Halo!"
    assert "speech_metadata" not in contents[0]["parts"][0]


def test_custom_voice_and_model_forwarded():
    client = _mock_client()
    backend = GeminiBackend(model="gemini-3.8-flash-tts", client=client)
    backend._synthesize_one(SynthesisRequest(text="Hi", voice="Aoede"))
    _, kwargs = client.models.generate_content.call_args
    assert kwargs["model"] == "gemini-3.8-flash-tts"
    voice_cfg = kwargs["config"].speech_config.voice_config
    assert voice_cfg.prebuilt_voice_config.voice_name == "Aoede"


def test_style_sets_speech_metadata():
    client = _mock_client()
    backend = GeminiBackend(client=client)
    backend._synthesize_one(SynthesisRequest(text="Hi", style="cheerful and friendly"))
    _, kwargs = client.models.generate_content.call_args
    part = kwargs["contents"][0]["parts"][0]
    assert part["speech_metadata"] == {"style": "cheerful and friendly"}
    # verbatim transcript rule: style never leaks into the text
    assert "cheerful" not in part["text"]


def test_text_parts_without_audio_are_skipped():
    text_part = SimpleNamespace(inline_data=None)
    audio_part = SimpleNamespace(inline_data=SimpleNamespace(data=b"RIFF-test"))
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(
        parts=[text_part, audio_part], prompt_feedback=None
    )
    backend = GeminiBackend(client=client)
    audio, _usage = backend._synthesize_one(SynthesisRequest(text="Hi"))
    assert audio == b"RIFF-test"


def test_empty_response_is_per_item_error():
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(
        parts=[], prompt_feedback="blocked"
    )
    backend = GeminiBackend(client=client)
    results = list(backend.synthesize_many([(1, SynthesisRequest(text="Hi"))]))
    assert len(results) == 1
    assert results[0].ok is False
    assert "no audio" in results[0].error


def test_sdk_error_maps_to_per_item_result():
    client = MagicMock()
    client.models.generate_content.side_effect = Exception("boom")
    backend = GeminiBackend(client=client)
    results = list(
        backend.synthesize_many(
            [(1, SynthesisRequest(text="a")), (2, SynthesisRequest(text="b"))]
        )
    )
    assert [r.ok for r in results] == [False, False]
    assert "boom" in results[0].error


def test_auth_error_aborts_whole_run():
    client = MagicMock()
    client.models.generate_content.side_effect = Exception("API key not valid")
    backend = GeminiBackend(client=client)
    with pytest.raises(RuntimeError, match="auth failed"):
        list(backend.synthesize_many([(1, SynthesisRequest(text="a"))]))
    # no pointless per-line retries after an auth failure
    assert client.models.generate_content.call_count == 1


def test_invalid_model_rejected():
    with pytest.raises(ValueError, match="model must be one of"):
        GeminiBackend(model="gemini-2.5-flash-preview-tts", client=MagicMock())


def test_cancel_stops_iteration():
    client = _mock_client()
    backend = GeminiBackend(client=client)
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 1

    results = list(
        backend.synthesize_many(
            [(1, SynthesisRequest(text="a")), (2, SynthesisRequest(text="b"))],
            cancel=cancel,
        )
    )
    assert [r.index for r in results] == [1]
    assert client.models.generate_content.call_count == 1


def _voice_entry(display_name="Kore", gender="female", language_code="en-US"):
    return SimpleNamespace(
        display_name=display_name, id=display_name.lower(),
        gender=gender, language_code=language_code, description=None,
    )


def test_list_voices_uses_flat_kwarg_and_maps_fields():
    client = MagicMock()
    client.voices.list.return_value = SimpleNamespace(
        voices=[_voice_entry(), _voice_entry("Aoede", "female", "en-US")]
    )
    backend = GeminiBackend(client=client)
    voices = backend.list_voices("en-US")
    client.voices.list.assert_called_once_with(language_code=["en-US"])
    assert [(v.name, v.gender, v.languages) for v in voices] == [
        ("Aoede", "female", ["en-US"]),
        ("Kore", "female", ["en-US"]),
    ]


def test_list_voices_falls_back_to_full_list_when_filter_matches_nothing():
    client = MagicMock()
    client.voices.list.side_effect = [
        SimpleNamespace(voices=[]),  # server-side filtered: nothing
        SimpleNamespace(voices=[_voice_entry()]),  # unfiltered retry
    ]
    backend = GeminiBackend(client=client)
    voices = backend.list_voices("id-ID")
    assert [v.name for v in voices] == ["Kore"]
    assert client.voices.list.call_count == 2


def test_list_voices_never_iterates_the_response_object():
    # Regression: iterating a pydantic response yields its fields, not voices.
    client = MagicMock()
    client.voices.list.return_value = SimpleNamespace(voices=None)
    backend = GeminiBackend(client=client)
    assert backend.list_voices() == []


def _usage_ns(prompt=29, candidates=92, audio_detail=True):
    cand_details = (
        [SimpleNamespace(modality=SimpleNamespace(name="AUDIO"), token_count=candidates)]
        if audio_detail
        else None
    )
    return SimpleNamespace(
        prompt_token_count=prompt,
        candidates_token_count=candidates,
        prompt_tokens_details=None,
        candidates_tokens_details=cand_details,
    )


def test_synthesize_many_attaches_usage_and_cost_fields():
    usage = _usage_ns()
    part = SimpleNamespace(inline_data=SimpleNamespace(data=b"RIFF-test"))
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(
        parts=[part], prompt_feedback=None, usage_metadata=usage
    )
    backend = GeminiBackend(client=client)
    results = list(backend.synthesize_many([(1, SynthesisRequest(text="Hi"))]))
    (result,) = results
    assert result.ok is True
    assert result.prompt_tokens == 29
    assert result.candidates_tokens == 92
    # F11 verify math: 29/1M×$0.50 + 92/1M×$6.00 (intro lite-TTS rates).
    assert result.estimated_cost_usd == pytest.approx(29 / 1e6 * 0.50 + 92 / 1e6 * 6.00)


def test_failed_items_have_no_cost_fields():
    client = MagicMock()
    client.models.generate_content.side_effect = Exception("boom")
    backend = GeminiBackend(client=client)
    results = list(backend.synthesize_many([(1, SynthesisRequest(text="a"))]))
    (result,) = results
    assert result.ok is False
    assert result.prompt_tokens is None
    assert result.candidates_tokens is None
    assert result.estimated_cost_usd is None


def test_missing_usage_metadata_yields_none_cost():
    client = _mock_client()  # SimpleNamespace parts only, no usage_metadata
    backend = GeminiBackend(client=client)
    results = list(backend.synthesize_many([(1, SynthesisRequest(text="Hi"))]))
    (result,) = results
    assert result.ok is True
    assert result.prompt_tokens is None
    assert result.estimated_cost_usd is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
