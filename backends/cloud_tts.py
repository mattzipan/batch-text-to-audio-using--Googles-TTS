"""Legacy Google Cloud TTS backend (google-cloud-texttospeech).

Optional fallback behind the same TTSBackend interface. Constructors accept an
injected client so tests never touch the network or a service-account file.
"""

import time

from google.cloud import texttospeech

from .base import SynthesisRequest, SynthesisResult, TTSBackend, VoiceInfo

DEFAULT_VOICE = "id-ID-Wavenet-A"


class CloudTTSBackend(TTSBackend):
    name = "cloud-tts"

    def __init__(self, client=None, service_account_file: str = "service-account.json"):
        if client is None:
            client = texttospeech.TextToSpeechClient.from_service_account_json(
                service_account_file
            )
        self.client = client

    def _synthesize_one(self, req: SynthesisRequest) -> bytes:
        if req.style:
            raise ValueError("cloud-tts backend does not support --style (Gemini only)")
        if not req.voice:
            raise ValueError("cloud-tts requires an explicit voice, e.g. id-ID-Wavenet-A")
        # Extract language code from voice name (e.g. 'id-ID' from
        # 'id-ID-Wavenet-A'); an explicit --language always wins.
        language_code = req.language or "-".join(req.voice.split("-")[:2])
        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code, name=req.voice
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=24000,
        )
        response = self.client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=req.text),
            voice=voice,
            audio_config=audio_config,
        )
        # LINEAR16 audio_content already includes the WAV header — write as-is.
        return response.audio_content

    def synthesize_many(self, items, *, progress=None, cancel=None):
        total = len(items)
        done = 0
        for index, req in items:
            if cancel is not None and cancel():
                return
            try:
                audio = self._synthesize_one(req)
            except Exception as exc:  # noqa: BLE001 - mapped to per-item result
                done += 1
                yield SynthesisResult(index=index, ok=False, error=str(exc))
            else:
                done += 1
                yield SynthesisResult(index=index, ok=True, audio=audio)
            if progress is not None:
                progress(done, total, req.text[:30])
            time.sleep(0.1)  # avoid flooding; Cloud TTS handles ~1000 RPM

    def list_voices(self, language: str | None = None) -> list[VoiceInfo]:
        response = self.client.list_voices()
        voices: list[VoiceInfo] = []
        for voice in response.voices or []:
            langs = list(getattr(voice, "language_codes", []) or [])
            if language and not any(
                lc == language or lc.startswith(language.split("-")[0]) for lc in langs
            ):
                continue
            gender = getattr(voice, "ssml_gender", None)
            voices.append(
                VoiceInfo(
                    name=voice.name,
                    gender=getattr(gender, "name", gender),
                    languages=langs,
                )
            )
        return sorted(voices, key=lambda v: v.name)
