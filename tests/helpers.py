"""Shared test doubles: a FakeBackend implementing the TTSBackend ABC."""

from backends.base import SynthesisRequest, SynthesisResult, TTSBackend, VoiceInfo  # noqa: F401


class FakeBackend(TTSBackend):
    name = "fake"

    def __init__(
        self,
        audio: bytes = b"RIFF-fake",
        fail_indexes: tuple[int, ...] = (),
        run_error: Exception | None = None,
        interrupt_at: int | None = None,
        voices: list[VoiceInfo] | None = None,
    ):
        self.audio = audio
        self.fail_indexes = set(fail_indexes)
        self.run_error = run_error
        self.interrupt_at = interrupt_at
        self.voices = voices if voices is not None else [
            VoiceInfo(name="Zed", gender="FEMALE", languages=["id-ID"])
        ]
        self.received: list[tuple[int, SynthesisRequest]] = []

    def synthesize_many(self, items, *, progress=None, cancel=None):
        if self.run_error is not None:
            raise self.run_error
        total = len(items)
        done = 0
        for index, req in items:
            if cancel is not None and cancel():
                return
            if self.interrupt_at == index:
                raise KeyboardInterrupt
            done += 1
            self.received.append((index, req))
            if index in self.fail_indexes:
                yield SynthesisResult(index=index, ok=False, error="fake failure")
            else:
                yield SynthesisResult(index=index, ok=True, audio=self.audio)
            if progress is not None:
                progress(done, total, req.text[:30])

    def list_voices(self, language: str | None = None) -> list[VoiceInfo]:
        return self.voices
