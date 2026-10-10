"""Tests for app.tts (task B2): cache generation via a FakeBackend."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.project import (
    audio_path,
    insert_row,
    new_project,
    set_variant_status,
    update_variant_text,
)
from app import tts
from app.tts import generate_audio
from tests.helpers import FakeBackend

AUDIO = b"RIFF-fake-wav-bytes"


def _make_project(folder: Path, statuses: tuple[str, str, str] = ("ok", "stale", "pending")):
    project = new_project(folder, "de", "id", False)
    project.voice = "Kore"
    project.target_lang = "id"
    texts = (("Guten Morgen", "Selamat pagi"), ("Danke", "Terima kasih"), ("Tschuss", "Dadah"))
    for source, translation in texts:
        insert_row(project, None, source, translation)
    for row, status in zip(project.rows, statuses):
        variant = row.variants[0]
        if status == "stale":
            update_variant_text(project, row.id, variant.id, variant.text + "!")
        else:
            set_variant_status(project, row.id, variant.id, status)
    return project


def _key(project, index: int) -> str:
    row = project.rows[index]
    return f"{row.id}:{row.variants[0].id}"


def test_stale_and_pending_regenerate_ok_skipped(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "p")
    backend = FakeBackend(audio=AUDIO)
    results = generate_audio(project, backend=backend)
    assert set(results) == {_key(project, 1), _key(project, 2)}
    assert all(value == "ok" for value in results.values())
    assert len(backend.received) == 2
    # Request shape: text/voice/language forwarded, no style.
    for _, request in backend.received:
        assert request.voice == "Kore"
        assert request.language == "id"
        assert request.style is None
    assert backend.received[0][1].text.endswith("!")
    # Statuses updated; the ok row was never touched.
    assert [row.variants[0].status for row in project.rows] == ["ok", "ok", "ok"]
    assert len([p for p in (project.folder / "audio").glob("*.wav")]) == 2


def test_force_regenerates_ok_rows(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "p")
    backend = FakeBackend(audio=AUDIO)
    results = generate_audio(project, force=True, backend=backend)
    assert set(results) == {_key(project, 0), _key(project, 1), _key(project, 2)}
    assert len(backend.received) == 3


def test_variant_ids_restricts_targets(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "p", ("pending", "pending", "pending"))
    only = project.rows[2].variants[0].id
    backend = FakeBackend(audio=AUDIO)
    results = generate_audio(project, variant_ids=[only], backend=backend)
    assert set(results) == {_key(project, 2)}
    assert len(backend.received) == 1
    assert backend.received[0][1].text == "Dadah"
    assert [row.variants[0].status for row in project.rows] == [
        "pending",
        "pending",
        "ok",
    ]


def test_cache_file_written_with_exact_bytes(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "p", ("pending", "ok", "ok"))
    backend = FakeBackend(audio=AUDIO)
    generate_audio(project, backend=backend)
    row = project.rows[0]
    cached = audio_path(project, row.id, row.variants[0].id)
    assert cached.is_file()
    assert cached.read_bytes() == AUDIO


def test_failure_sets_error_status(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "p", ("pending", "pending", "ok"))
    backend = FakeBackend(audio=AUDIO, fail_indexes=(1,))
    results = generate_audio(project, backend=backend)
    assert results[_key(project, 0)] == "fake failure"
    assert results[_key(project, 1)] == "ok"
    assert [row.variants[0].status for row in project.rows] == ["error", "ok", "ok"]


def test_progress_called_per_item(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "p", ("pending", "stale", "ok"))
    seen: list[tuple[int, int, str]] = []
    backend = FakeBackend(audio=AUDIO)
    generate_audio(project, progress=lambda d, t, m: seen.append((d, t, m)), backend=backend)
    assert [(done, total) for done, total, _ in seen] == [(1, 2), (2, 2)]
    assert all(isinstance(message, str) for _, _, message in seen)


def test_cancel_stops_iteration(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "p", ("pending", "pending", "pending"))
    backend = FakeBackend(audio=AUDIO)
    results = generate_audio(project, cancel=lambda: True, backend=backend)
    assert results == {}
    assert backend.received == []
    assert {row.variants[0].status for row in project.rows} == {"pending"}


def test_empty_project_never_touches_backend(tmp_path: Path) -> None:
    project = new_project(tmp_path / "empty", "de", "id", False)
    backend = FakeBackend(audio=AUDIO, run_error=RuntimeError("must not be called"))
    assert generate_audio(project, backend=backend) == {}
    assert backend.received == []


def test_all_ok_without_force_never_touches_backend(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "p", ("ok", "ok", "ok"))
    backend = FakeBackend(audio=AUDIO, run_error=RuntimeError("must not be called"))
    assert generate_audio(project, backend=backend) == {}
    assert backend.received == []


def test_test_voice_returns_bytes() -> None:
    backend = FakeBackend(audio=AUDIO)
    assert tts.test_voice("Kore", "gemini-3.8-flash-lite-tts", "halo", backend=backend) == AUDIO
    assert backend.received[0][1].voice == "Kore"
    assert backend.received[0][1].text == "halo"


def test_test_voice_raises_on_error() -> None:
    backend = FakeBackend(audio=AUDIO, fail_indexes=(1,))
    with pytest.raises(RuntimeError, match="fake failure"):
        tts.test_voice("Kore", "gemini-3.8-flash-lite-tts", "halo", backend=backend)
