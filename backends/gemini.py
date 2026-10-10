"""Gemini 3.8 TTS backend (google-genai SDK, Gemini API).

Uses synchronous generate_content with AUDIO response modality, one request
per line. Unary output is already a complete WAV (24 kHz mono 16-bit LE) and
is returned byte-for-byte — never wrapped or converted here.
"""

import base64
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from .base import SynthesisRequest, SynthesisResult, TTSBackend, VoiceInfo

VALID_MODELS = ("gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts")
DEFAULT_MODEL = "gemini-3.8-flash-lite-tts"
DEFAULT_VOICE = "Kore"

# Per-item retry for transient failures: attempts sleep 2s, 4s, 8s.
_MAX_RETRIES = 3


def _is_auth_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if code in (401, 403):
        return True
    text = f"{type(exc).__name__}: {exc}".lower()
    return "api key not valid" in text or "unauthenticated" in text


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, genai_errors.ServerError):
        return True
    code = getattr(exc, "code", None)
    if code == 429 or (isinstance(code, int) and 500 <= code < 600):
        return True
    text = f"{type(exc).__name__}: {exc}".lower()
    return "resource_exhausted" in text or "unavailable" in text or "too many requests" in text


class GeminiBackend(TTSBackend):
    name = "gemini"

    def __init__(self, model: str = DEFAULT_MODEL, client=None):
        if model not in VALID_MODELS:
            raise ValueError(f"model must be one of {VALID_MODELS}, got {model!r}")
        self.model = model
        # genai.Client() reads GEMINI_API_KEY (or GOOGLE_API_KEY) from the env.
        self.client = client or genai.Client()

    def _synthesize_one(self, req: SynthesisRequest) -> bytes:
        # The text is a verbatim transcript: no style/prompt is ever injected.
        part: dict = {"text": req.text}
        if req.style:
            part["speech_metadata"] = {"style": req.style}
        contents = [{"role": "user", "parts": [part]}]
        # NOTE: GenerateContentConfig has no response_format field (that is
        # Interactions-API only). The unary default is WAV, which is what we want.
        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=req.voice or DEFAULT_VOICE
                    )
                )
            ),
        )
        response = self.client.models.generate_content(
            model=self.model, contents=contents, config=config
        )
        # Never call response.text here — it raises on audio-only responses.
        for p in response.parts or []:
            data = getattr(p.inline_data, "data", None) if p.inline_data else None
            if not data:
                continue
            if isinstance(data, str):  # some SDK versions return base64 text
                data = base64.b64decode(data)
            return data  # complete WAV bytes — return as-is, no header wrapping
        raise RuntimeError(
            f"no audio in response (prompt_feedback={response.prompt_feedback})"
        )

    def synthesize_many(self, items, *, progress=None, cancel=None):
        total = len(items)
        done = 0
        for index, req in items:
            if cancel is not None and cancel():
                return
            last_error: Exception | None = None
            audio: bytes | None = None
            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    audio = self._synthesize_one(req)
                    last_error = None
                    break
                except Exception as exc:  # noqa: BLE001 - mapped to per-item result
                    if _is_auth_error(exc):
                        # Whole-run failure: retrying every line is pointless.
                        raise RuntimeError(f"Gemini API auth failed: {exc}") from exc
                    last_error = exc
                    if _is_transient(exc) and attempt < _MAX_RETRIES:
                        time.sleep(2 * attempt)
                    else:
                        break
            done += 1
            if last_error is not None:
                yield SynthesisResult(index=index, ok=False, error=str(last_error))
            else:
                assert audio is not None
                yield SynthesisResult(index=index, ok=True, audio=audio)
            if progress is not None:
                progress(done, total, req.text[:30])

    @staticmethod
    def _to_voice_info(entry) -> VoiceInfo:
        # language_code is a single BCP-47 string (e.g. "en-US") on Voice entries.
        langs = getattr(entry, "language_code", None) or []
        if isinstance(langs, str):
            langs = [langs]
        gender = getattr(entry, "gender", None)
        return VoiceInfo(
            name=getattr(entry, "display_name", None)
            or getattr(entry, "id", None)
            or "?",
            gender=getattr(gender, "name", gender),
            languages=list(langs),
            note=getattr(entry, "description", None),
        )

    @staticmethod
    def _matches_language(voice: VoiceInfo, language: str) -> bool:
        prefix = language.split("-")[0].lower()
        return any(
            lc.lower() == language.lower() or lc.lower().startswith(prefix)
            for lc in voice.languages
        )

    def list_voices(self, language: str | None = None) -> list[VoiceInfo]:
        list_fn = getattr(self.client.voices, "list", None)
        if list_fn is None:
            raise RuntimeError("google-genai>=2.25.0 is required for voices.list")
        if language:
            response = list_fn(language_code=[language])
        else:
            response = list_fn()
        # NOTE: getattr default is [] — never fall back to iterating `response`
        # itself (a pydantic model iterates its fields, producing garbage rows).
        entries = getattr(response, "voices", None) or []
        voices = [self._to_voice_info(e) for e in entries]
        if language:
            matched = [v for v in voices if self._matches_language(v, language)]
            if not matched:
                # Server-side filter may be ignored; retry unfiltered and
                # match client-side.
                entries = getattr(list_fn(), "voices", None) or []
                voices = [self._to_voice_info(e) for e in entries]
                matched = [v for v in voices if self._matches_language(v, language)]
            # Still nothing (e.g. no id-ID-tagged voices exist yet): prebuilt
            # voices speak any supported language via auto-detect, so show all.
            voices = matched or voices
        return sorted(voices, key=lambda v: v.name)
