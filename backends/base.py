"""Backend abstraction for batch text-to-speech.

Both the CLI (batch_generate_audio.py) and the future interface import this
package directly. Keep it free of CLI imports, global state, and prints.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Iterator


@dataclass
class SynthesisRequest:
    text: str
    voice: str | None = None      # backend-specific voice name
    language: str | None = None   # BCP-47 like "id-ID"; None = auto-detect
    style: str | None = None      # sustained delivery hint (Gemini only)


@dataclass
class SynthesisResult:
    index: int                    # 1-based line number
    ok: bool
    audio: bytes | None = None    # complete WAV bytes when ok
    error: str | None = None


@dataclass
class VoiceInfo:
    name: str
    gender: str | None = None
    languages: list[str] = field(default_factory=list)
    note: str | None = None


class TTSBackend(ABC):
    name: str  # "gemini" or "cloud-tts"

    @abstractmethod
    def synthesize_many(
        self,
        items: list[tuple[int, SynthesisRequest]],
        *,
        progress: Callable[[int, int, str], None] | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> Iterator[SynthesisResult]:
        """Yield one SynthesisResult per item, in input order.

        progress(done, total, message) is called after every item.
        cancel() is checked before each request; when it returns True,
        stop and return (already-yielded results stand).
        Per-item API failures MUST be yielded as SynthesisResult(ok=False),
        never raised. Raise exceptions only for whole-run failures
        (missing/invalid credentials, missing service-account file).
        """

    @abstractmethod
    def list_voices(self, language: str | None = None) -> list[VoiceInfo]:
        """Return available voices, optionally filtered by BCP-47 language."""
