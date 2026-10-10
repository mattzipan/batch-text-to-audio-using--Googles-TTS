"""Cloud TTS backend tests: request mapping, style rejection (mocked)."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.cloud import texttospeech  # noqa: E402

from backends.base import SynthesisRequest  # noqa: E402
from backends.cloud_tts import CloudTTSBackend, DEFAULT_VOICE  # noqa: E402


def _mock_client(audio: bytes = b"RIFF-cloud"):
    client = MagicMock()
    client.synthesize_speech.return_value = SimpleNamespace(audio_content=audio)
    return client


def test_default_voice_constant():
    assert DEFAULT_VOICE == "id-ID-Wavenet-A"


def test_request_mapping_and_language_inference():
    client = _mock_client()
    backend = CloudTTSBackend(client=client)
    result = backend._synthesize_one(
        SynthesisRequest(text="Halo!", voice="id-ID-Wavenet-A")
    )
    assert result == b"RIFF-cloud"
    _, kwargs = client.synthesize_speech.call_args
    assert kwargs["voice"].name == "id-ID-Wavenet-A"
    assert kwargs["voice"].language_code == "id-ID"
    assert kwargs["audio_config"].sample_rate_hertz == 24000
    assert kwargs["audio_config"].audio_encoding == texttospeech.AudioEncoding.LINEAR16
    assert kwargs["input"].text == "Halo!"


def test_explicit_language_wins_over_inference():
    client = _mock_client()
    backend = CloudTTSBackend(client=client)
    backend._synthesize_one(
        SynthesisRequest(text="Halo!", voice="id-ID-Wavenet-A", language="ms-MY")
    )
    _, kwargs = client.synthesize_speech.call_args
    assert kwargs["voice"].language_code == "ms-MY"


def test_style_rejected():
    client = _mock_client()
    backend = CloudTTSBackend(client=client)
    results = list(
        backend.synthesize_many(
            [(1, SynthesisRequest(text="Hi", voice="id-ID-Wavenet-A", style="warm"))]
        )
    )
    assert len(results) == 1
    assert results[0].ok is False
    assert "does not support --style" in results[0].error
    client.synthesize_speech.assert_not_called()


def test_missing_voice_rejected():
    client = _mock_client()
    backend = CloudTTSBackend(client=client)
    results = list(backend.synthesize_many([(1, SynthesisRequest(text="Hi"))]))
    assert results[0].ok is False
    assert "explicit voice" in results[0].error


def test_results_in_input_order_with_progress():
    client = _mock_client()
    backend = CloudTTSBackend(client=client)
    seen: list[tuple[int, int, str]] = []
    results = list(
        backend.synthesize_many(
            [(3, SynthesisRequest(text="c", voice="id-ID-Wavenet-A")),
             (1, SynthesisRequest(text="a", voice="id-ID-Wavenet-A"))],
            progress=lambda done, total, msg: seen.append((done, total, msg)),
        )
    )
    assert [r.index for r in results] == [3, 1]
    assert all(r.ok for r in results)
    assert seen == [(1, 2, "c"), (2, 2, "a")]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
