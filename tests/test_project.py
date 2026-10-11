"""Tests for app.project (task A2): roundtrip, row ops, stale marking."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.project import (
    PROJECT_FILENAME,
    audio_path,
    delete_row,
    insert_row,
    load_project,
    move_row,
    new_project,
    save_project,
    set_variant_status,
    update_variant_text,
)

HEX6 = re.compile(r"^[0-9a-f]{6}$")


def _make_project(folder: Path):
    project = new_project(folder, "de", "id", False)
    insert_row(project, None, "Guten Morgen", "Selamat pagi")
    insert_row(project, None, "Danke", "Terima kasih")
    insert_row(project, None, "Tschüss", "Dadah")
    return project


def _sources(project) -> list[str]:
    return [row.source for row in project.rows]


def test_save_load_roundtrip(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "demo")
    for row in project.rows:
        set_variant_status(project, row.id, row.variants[0].id, "ok")
    project.repeats = 5

    target = save_project(project)
    assert target.name == PROJECT_FILENAME
    assert (project.folder / "audio").is_dir()
    assert (project.folder / "audio").is_dir()  # built tracks live in the export dir, not here
    assert not (project.folder / (PROJECT_FILENAME + ".tmp")).exists()

    raw = json.loads((project.folder / PROJECT_FILENAME).read_text(encoding="utf-8"))
    assert "folder" not in raw  # folder is implied by location, not stored
    assert raw["version"] == 1
    assert [r["position"] for r in raw["rows"]] == [1, 2, 3]

    loaded = load_project(project.folder)
    assert loaded.folder == project.folder
    assert (loaded.source_lang, loaded.target_lang) == ("de", "id")
    assert loaded.variants_enabled is False
    assert (loaded.tts_model, loaded.voice) == (project.tts_model, project.voice)
    assert (loaded.repeats, loaded.repeat_gap_s, loaded.item_gap_s) == (5, 1.2, 1.8)
    assert _sources(loaded) == ["Guten Morgen", "Danke", "Tschüss"]
    assert [row.position for row in loaded.rows] == [1, 2, 3]
    assert [row.variants[0].text for row in loaded.rows] == [
        "Selamat pagi",
        "Terima kasih",
        "Dadah",
    ]
    assert {v.status for row in loaded.rows for v in row.variants} == {"ok"}
    assert [row.id for row in loaded.rows] == [row.id for row in project.rows]


def test_insert_before_n_append_and_renumber(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "p")
    assert [row.position for row in project.rows] == [1, 2, 3]

    inserted = insert_row(project, 2, "Bitte", "Tolong")
    assert _sources(project) == ["Guten Morgen", "Bitte", "Danke", "Tschüss"]
    assert [row.position for row in project.rows] == [1, 2, 3, 4]
    assert project.rows[1].id == inserted.id
    assert inserted.variants[0].style == "main"
    assert inserted.variants[0].text == "Tolong"
    assert inserted.variants[0].status == "pending"

    appended = insert_row(project, None, "Ja")
    assert project.rows[-1].id == appended.id
    assert appended.variants[0].text == ""
    assert [row.position for row in project.rows] == [1, 2, 3, 4, 5]

    past_end = insert_row(project, 999, "Nein")
    assert project.rows[-1].id == past_end.id
    assert [row.position for row in project.rows] == [1, 2, 3, 4, 5, 6]


def test_row_ids_unique_hex_and_stable(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "p")
    ids = [row.id for row in project.rows]
    vids = [v.id for row in project.rows for v in row.variants]
    assert len(set(ids + vids)) == len(ids) + len(vids)
    assert all(HEX6.match(i) for i in ids + vids)
    # Ids never derive from display position: moving rows keeps every id.
    move_row(project, project.rows[0].id, "down")
    assert [row.id for row in project.rows] == [ids[1], ids[0], ids[2]]
    assert [row.position for row in project.rows] == [1, 2, 3]


def test_delete_row_removes_audio_and_renumbers(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "p")
    save_project(project)  # creates audio/
    victim = project.rows[1]
    paths = [audio_path(project, victim.id, v.id) for v in victim.variants]
    assert paths[0] == project.folder / "audio" / f"{victim.id}_{victim.variants[0].id}.wav"
    for path in paths:
        path.write_bytes(b"fake-wav")
    other = audio_path(project, project.rows[0].id, project.rows[0].variants[0].id)
    other.write_bytes(b"keep-me")

    removed = delete_row(project, victim.id)
    assert removed.id == victim.id
    assert _sources(project) == ["Guten Morgen", "Tschüss"]
    assert [row.position for row in project.rows] == [1, 2]
    assert all(not p.exists() for p in paths)
    assert other.exists()  # unrelated cache files are untouched

    with pytest.raises(ValueError):
        delete_row(project, "nope")
    # Deleting a row whose audio was never generated must not raise.
    delete_row(project, project.rows[0].id)
    assert _sources(project) == ["Tschüss"]


def test_move_up_down_and_boundaries(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "p")

    assert move_row(project, project.rows[0].id, "up") is False  # first: no-op
    assert _sources(project) == ["Guten Morgen", "Danke", "Tschüss"]
    assert move_row(project, project.rows[-1].id, "down") is False  # last: no-op
    assert _sources(project) == ["Guten Morgen", "Danke", "Tschüss"]

    assert move_row(project, project.rows[0].id, "down") is True
    assert _sources(project) == ["Danke", "Guten Morgen", "Tschüss"]
    assert [row.position for row in project.rows] == [1, 2, 3]

    assert move_row(project, project.rows[-1].id, "up") is True
    assert _sources(project) == ["Danke", "Tschüss", "Guten Morgen"]
    assert [row.position for row in project.rows] == [1, 2, 3]

    with pytest.raises(ValueError):
        move_row(project, project.rows[0].id, "sideways")
    with pytest.raises(ValueError):
        move_row(project, "nope", "up")


def test_update_variant_text_marks_stale(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "p")
    row = project.rows[0]
    variant = row.variants[0]
    set_variant_status(project, row.id, variant.id, "ok")

    updated = update_variant_text(project, row.id, variant.id, "Selamat pagi!")
    assert updated.text == "Selamat pagi!"
    assert updated.status == "stale"
    assert row.variants[0].status == "stale"

    with pytest.raises(ValueError):
        update_variant_text(project, row.id, "nope", "x")


def test_set_variant_status_roundtrip_and_rejects_bad(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "p")
    row = project.rows[0]
    for status in ("pending", "generating", "ok", "stale", "error"):
        assert set_variant_status(project, row.id, row.variants[0].id, status).status == status
    with pytest.raises(ValueError):
        set_variant_status(project, row.id, row.variants[0].id, "done")


def test_load_repairs_duplicate_ids(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "p")
    project.rows[1].id = project.rows[0].id  # simulate a hand-edited collision
    save_project(project)

    loaded = load_project(project.folder)
    ids = [row.id for row in loaded.rows]
    vids = [v.id for row in loaded.rows for v in row.variants]
    assert len(set(ids + vids)) == len(ids) + len(vids)


def test_export_dir_music_and_fallback(tmp_path, monkeypatch):
    """Exports go to the Music dir; fallback output/ next to the app."""
    from app import config

    music = tmp_path / "Music"
    music.mkdir()
    monkeypatch.setenv("XDG_MUSIC_DIR", str(music))
    monkeypatch.delenv("WORDTAPE_EXPORT_DIR", raising=False)
    assert config.export_dir("demo") == music / "WordTape" / "demo"

    monkeypatch.setenv("XDG_MUSIC_DIR", str(tmp_path / "gone"))  # unavailable
    monkeypatch.setattr(config, "app_root", lambda: tmp_path / "approot")
    assert config.export_dir("demo") == tmp_path / "approot" / "output" / "demo"

    monkeypatch.setenv("WORDTAPE_EXPORT_DIR", str(tmp_path / "custom"))
    assert config.export_dir("demo") == tmp_path / "custom" / "demo"


def test_export_dir_makes_no_dirs(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setenv("WORDTAPE_EXPORT_DIR", str(tmp_path / "never"))
    config.export_dir("demo")
    assert not (tmp_path / "never").exists()
