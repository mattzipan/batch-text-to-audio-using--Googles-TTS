"""WordTape TTS service: per-variant audio cache driven by ``backends/``.

Thin wrapper only — no TTS request code lives here. :func:`generate_audio`
collects the (row, variant) pairs that need synthesis, maps stable variant
ids onto the 1-based ``index`` field of :class:`SynthesisRequest` items, and
writes the returned WAV bytes to :func:`app.project.audio_path`.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from typing import TYPE_CHECKING

from app.project import Project, audio_path, set_variant_status

if TYPE_CHECKING:  # imported lazily at runtime to keep this module light
    from backends.base import TTSBackend, VoiceInfo

_RETRYABLE_STATUSES = ("pending", "stale")

ProgressFn = Callable[[int, int, str], None]
CancelFn = Callable[[], bool]


def _fill_cost_outparam(collect_cost: dict | None, results) -> None:
    """Fill a caller-supplied ``collect_cost`` out-param from result costs.

    Contract: on a completed run the dict gets ``"usd"`` (float — the sum of
    per-result ``estimated_cost_usd``, skipping ``None``) and ``"known"``
    (True iff at least one result carried a non-None estimate). Callers must
    show an ``est.`` suffix only when ``known`` is True — never render
    ``$0.00`` for unknown cost. On a whole-run exception the dict is left
    untouched. Estimates are local (usage × pricing table), never billed cost.
    """
    if collect_cost is None:
        return
    total = 0.0
    known = False
    for result in results:
        cost = getattr(result, "estimated_cost_usd", None)
        if cost is None:
            continue
        total += float(cost)
        known = True
    collect_cost["usd"] = round(total, 6)
    collect_cost["known"] = known


def generate_audio(
    project: Project,
    variant_ids: Collection[str] | None = None,
    force: bool = False,
    progress: ProgressFn | None = None,
    cancel: CancelFn | None = None,
    backend: TTSBackend | None = None,
    collect_cost: dict | None = None,
) -> dict[str, str]:
    """Synthesize missing/stale variant audio into the project cache.

    Targets are variants with status ``pending``/``stale`` (plus ``ok``
    when ``force`` is true). When ``variant_ids`` is given, only variants
    whose id — or ``"row_id:variant_id"`` key — is listed are considered.

    Returns a map of ``"row_id:variant_id"`` to ``"ok"`` or an error message.
    An empty target list returns ``{}`` without touching the backend (so no
    client is constructed and no credentials are needed).

    When ``collect_cost`` is given (optional out-param, return shape
    unchanged), it is filled on a completed run with ``"usd"`` (float sum of
    per-result estimates, ``0.0`` when nothing was costed) and ``"known"``
    (True iff at least one result carried an estimate). On a whole-run
    exception the dict is left untouched. See :func:`_fill_cost_outparam`.
    """
    from backends.base import SynthesisRequest

    wanted: set[str] | None = set(variant_ids) if variant_ids is not None else None
    targets: list[tuple[str, str, str]] = []  # (key, row_id, variant_id)
    items: list[tuple[int, SynthesisRequest]] = []
    seq = 0
    for row in project.rows:
        for variant in row.variants:
            key = f"{row.id}:{variant.id}"
            if wanted is not None and variant.id not in wanted and key not in wanted:
                continue
            if variant.status in _RETRYABLE_STATUSES or (
                force and variant.status == "ok"
            ):
                seq += 1
                targets.append((key, row.id, variant.id))
                items.append(
                    (
                        seq,
                        SynthesisRequest(
                            text=variant.text,
                            voice=project.voice,
                            language=project.target_lang,
                            style=None,
                        ),
                    )
                )
    if not items:
        _fill_cost_outparam(collect_cost, [])
        return {}

    if backend is None:
        from backends.gemini import GeminiBackend

        backend = GeminiBackend(model=project.tts_model)

    by_index: dict[int, tuple[str, str, str]] = {
        seq_no: targets[seq_no - 1] for seq_no, _ in items
    }
    results: dict[str, str] = {}
    synth_results = []
    for result in backend.synthesize_many(items, progress=progress, cancel=cancel):
        synth_results.append(result)
        key, row_id, variant_id = by_index[result.index]
        if result.ok and result.audio is not None:
            dest = audio_path(project, row_id, variant_id)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as handle:
                handle.write(result.audio)
            set_variant_status(project, row_id, variant_id, "ok")
            results[key] = "ok"
        else:
            message = result.error or "empty audio response"
            set_variant_status(project, row_id, variant_id, "error")
            results[key] = message
    _fill_cost_outparam(collect_cost, synth_results)
    return results


def test_voice(
    voice: str,
    model: str,
    text: str,
    backend: TTSBackend | None = None,
    collect_cost: dict | None = None,
) -> bytes:
    """Synthesize one short clip and return its WAV bytes (not cached).

    When ``collect_cost`` is given (optional out-param, return shape
    unchanged), it is filled on success with ``"usd"`` (float estimate for
    the clip, ``0.0`` when the backend reported no usage) and ``"known"``
    (True iff the result carried an estimate). On failure the dict is left
    untouched (the exception propagates). See :func:`_fill_cost_outparam`.
    """
    from backends.base import SynthesisRequest

    if backend is None:
        from backends.gemini import GeminiBackend

        backend = GeminiBackend(model=model)
    request = SynthesisRequest(text=text, voice=voice, language=None, style=None)
    for result in backend.synthesize_many([(1, request)]):
        if result.ok and result.audio is not None:
            _fill_cost_outparam(collect_cost, [result])
            return result.audio
        raise RuntimeError(result.error or "empty audio response")
    raise RuntimeError("test voice produced no audio")


def list_voices(
    model: str = "gemini-3.8-flash-lite-tts", language: str | None = None
) -> list[VoiceInfo]:
    """List available voices via a live ``GeminiBackend`` (real client)."""
    from backends.gemini import GeminiBackend

    return GeminiBackend(model=model).list_voices(language)
