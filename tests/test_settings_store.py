"""Tests for app/settings_store.py + the settings-backed config helpers (F7/F8).

All filesystem access is isolated via a tmp ``XDG_DATA_HOME``; no live API
calls and no real credentials are involved (the baked key is a fake module).
"""

from __future__ import annotations

import importlib
import stat
import sys
import types

import pytest

from app import config, settings_store

_DEFAULTS = {"gemini_api_key": None, "export_root": None}


@pytest.fixture()
def _xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    yield tmp_path


# --- settings_store roundtrip ---------------------------------------------


def test_roundtrip_and_permissions(_xdg):
    assert settings_store.load() == _DEFAULTS

    saved = settings_store.save({"gemini_api_key": "setting-key-123456"})
    assert saved["gemini_api_key"] == "setting-key-123456"

    path = settings_store.settings_path()
    assert path.is_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) & 0o077 == 0

    loaded = settings_store.load()
    assert loaded["gemini_api_key"] == "setting-key-123456"
    assert loaded["export_root"] is None

    # Merging a patch keeps the untouched keys.
    settings_store.save({"export_root": "/tmp/wordtape-root"})
    loaded = settings_store.load()
    assert loaded["gemini_api_key"] == "setting-key-123456"
    assert loaded["export_root"] == "/tmp/wordtape-root"

    # Atomic write leaves no stray tmp files behind.
    assert sorted(p.name for p in path.parent.iterdir()) == ["settings.json"]


def test_clear_is_set_null(_xdg):
    settings_store.save({"gemini_api_key": "setting-key-123456"})
    settings_store.save({"gemini_api_key": None})
    assert settings_store.load()["gemini_api_key"] is None

    settings_store.save({"gemini_api_key": "setting-key-123456"})
    settings_store.save({"gemini_api_key": ""})
    assert settings_store.load()["gemini_api_key"] is None


def test_load_missing_corrupt_and_wrong_types(_xdg):
    assert settings_store.load() == _DEFAULTS

    path = settings_store.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert settings_store.load() == _DEFAULTS

    path.write_text('["a list"]', encoding="utf-8")
    assert settings_store.load() == _DEFAULTS

    path.write_text(
        '{"gemini_api_key": 12345, "export_root": "", "other": "x"}',
        encoding="utf-8",
    )
    assert settings_store.load() == _DEFAULTS

    # Unknown keys in the patch are ignored by save().
    settings_store.save({"bogus": "ignored"})
    assert set(settings_store.load()) == set(_DEFAULTS)


def test_import_is_lazy_and_credential_free(_xdg):
    settings_store.save({"gemini_api_key": "setting-key-123456"})
    reloaded = importlib.reload(settings_store)
    scalars = [
        repr(value)
        for value in vars(reloaded).values()
        if not callable(value) and not isinstance(value, type)
    ]
    assert not any("setting-key-123456" in item for item in scalars)

    # Import never creates the file when it does not exist yet.
    settings_store.settings_path().unlink()
    importlib.reload(settings_store)
    assert not settings_store.settings_path().exists()


# --- key precedence: setting → env → baked --------------------------------


def test_api_key_precedence_setting_env_baked(_xdg, monkeypatch):
    fake_secrets = types.ModuleType("app.secrets")
    fake_secrets.API_KEY = "baked-key-99999999"  # type: ignore[attr-defined]
    import app as app_pkg

    monkeypatch.setitem(sys.modules, "app.secrets", fake_secrets)
    monkeypatch.setattr(app_pkg, "secrets", fake_secrets, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "env-key-88888888")

    # env beats baked
    assert config.get_api_key() == "env-key-88888888"

    # user setting beats env
    settings_store.save({"gemini_api_key": "setting-key-77777777"})
    assert config.get_api_key() == "setting-key-77777777"

    # clearing the setting falls back to env again
    settings_store.save({"gemini_api_key": None})
    assert config.get_api_key() == "env-key-88888888"

    # without env, the baked key is the last resort
    monkeypatch.delenv("GEMINI_API_KEY")
    assert config.get_api_key() == "baked-key-99999999"


def test_get_api_key_raises_without_any_source(_xdg, monkeypatch):
    fake_secrets = types.ModuleType("app.secrets")  # no API_KEY attribute
    import app as app_pkg

    monkeypatch.setitem(sys.modules, "app.secrets", fake_secrets)
    monkeypatch.setattr(app_pkg, "secrets", fake_secrets, raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(RuntimeError):
        config.get_api_key()


# --- export_dir precedence: settings → env → Music → app output -----------


def test_export_dir_precedence_chain(_xdg, monkeypatch):
    tmp_path = _xdg
    music = tmp_path / "Music"
    music.mkdir()
    monkeypatch.setenv("XDG_MUSIC_DIR", str(music))
    monkeypatch.setattr(config, "app_root", lambda: tmp_path / "approot")
    monkeypatch.delenv("WORDTAPE_EXPORT_DIR", raising=False)

    # 1. defaults: Music/WordTape/<project>
    assert config.export_dir("demo") == music / "WordTape" / "demo"

    # 2. env beats Music
    monkeypatch.setenv("WORDTAPE_EXPORT_DIR", str(tmp_path / "envroot"))
    assert config.export_dir("demo") == tmp_path / "envroot" / "demo"

    # 3. saved export_root beats env
    settings_store.save({"export_root": str(tmp_path / "setroot")})
    assert config.export_dir("demo") == tmp_path / "setroot" / "demo"
    assert config.export_root() == tmp_path / "setroot"

    # 4. clearing settings returns to env; no env -> Music; no Music -> app output
    settings_store.save({"export_root": None})
    assert config.export_dir("demo") == tmp_path / "envroot" / "demo"
    monkeypatch.delenv("WORDTAPE_EXPORT_DIR", raising=False)
    assert config.export_dir("demo") == music / "WordTape" / "demo"
    monkeypatch.setenv("XDG_MUSIC_DIR", str(tmp_path / "gone"))
    assert config.export_dir("demo") == tmp_path / "approot" / "output" / "demo"

    # export_dir never creates directories (spec F8 / test_project contract)
    assert not (tmp_path / "approot" / "output").exists()


def test_default_export_root_matches_export_root_default(_xdg, monkeypatch):
    tmp_path = _xdg
    music = tmp_path / "Music"
    music.mkdir()
    monkeypatch.setenv("XDG_MUSIC_DIR", str(music))
    assert config.default_export_root() == music / "WordTape"
    assert config.export_root() == config.default_export_root()
