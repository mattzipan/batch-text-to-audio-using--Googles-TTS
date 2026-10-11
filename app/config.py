"""WordTape global configuration: constants, paths, API key resolution."""

import os
import sys
from pathlib import Path

APP_NAME = "WordTape"
TRANSLATION_MODEL = "gemini-3.5-flash-lite"
TTS_MODELS = ("gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts")
DEFAULT_VOICE = "Kore"
REPEATS, REPEAT_GAP_S, ITEM_GAP_S = 5, 1.2, 1.8
DEFAULT_SOURCE_LANG, DEFAULT_TARGET_LANG = "de", "id"


def resource_path(rel: str) -> Path:
    """Resolve a bundled resource path (PyInstaller-safe via sys._MEIPASS)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / rel


def get_api_key() -> str:
    """Return the Gemini API key: user setting → env → app/secrets.py.

    ``GOOGLE_API_KEY`` is deliberately ignored (documented in README).

    Raises:
        RuntimeError: If none of the sources provides a non-empty key.
    """
    from app import settings_store

    user_key: str | None = settings_store.load().get("gemini_api_key")
    if user_key:
        return user_key
    env_key: str | None = os.environ.get("GEMINI_API_KEY")
    if env_key:
        return env_key
    try:
        from app import secrets
    except ImportError:
        secrets = None  # type: ignore[assignment]
    if secrets is not None:
        file_key: str | None = getattr(secrets, "API_KEY", None)
        if file_key:
            return file_key
    raise RuntimeError(
        "Gemini API key not found. Save one in Settings (⚙), set the "
        "GEMINI_API_KEY environment variable, or copy app/secrets.example.py "
        "to app/secrets.py and set API_KEY there."
    )


def app_root() -> Path:
    """Writable app directory: the exe's folder when frozen, repo root in dev.

    Nothing is ever written outside this tree except exported tracks in the
    system Music directory (see export_dir).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def projects_root() -> Path:
    """Working data root (project.json + per-translation audio cache)."""
    root = Path(os.environ["WORDTAPE_DATA_DIR"]) if os.environ.get("WORDTAPE_DATA_DIR") \
        else app_root() / "projects"
    root.mkdir(parents=True, exist_ok=True)
    return root


def music_dir() -> Path | None:
    """System Music directory if available, else None (XDG-aware)."""
    raw = os.environ.get("XDG_MUSIC_DIR")
    if not raw:
        cfg = Path.home() / ".config" / "user-dirs.dirs"
        if cfg.is_file():
            for line in cfg.read_text().splitlines():
                if line.startswith("XDG_MUSIC_DIR="):
                    raw = line.split("=", 1)[1].strip().strip('"')
                    raw = raw.replace("$HOME", str(Path.home()))
                    break
    cand = Path(raw) if raw else Path.home() / "Music"
    return cand if cand.is_dir() else None


def default_export_root() -> Path:
    """Default export root (no settings/env override): Music/WordTape else output/."""
    music = music_dir()
    return (music / APP_NAME) if music else (app_root() / "output")


def export_root() -> Path:
    """Export root: settings.export_root → env WORDTAPE_EXPORT_DIR → default.

    The settings root is machine-specific (spec F8); nothing is created here.
    """
    from app import settings_store

    saved: str | None = settings_store.load().get("export_root")
    if saved:
        return Path(saved)
    env = os.environ.get("WORDTAPE_EXPORT_DIR")
    if env:
        return Path(env)
    return default_export_root()


def export_dir(project_name: str) -> Path:
    """Final track destination: <export_root>/<project>/ (see export_root)."""
    return export_root() / project_name


_env_before_apply: str | None = None
_env_before_apply_set = False


def apply_api_key_to_env() -> str:
    """Resolve the API key via get_api_key() and export it as GEMINI_API_KEY."""
    global _env_before_apply, _env_before_apply_set
    if not _env_before_apply_set:
        _env_before_apply = os.environ.get("GEMINI_API_KEY")
        _env_before_apply_set = True
    key: str = get_api_key()
    os.environ["GEMINI_API_KEY"] = key
    return key


def restore_env_key(cleared_key: str | None) -> None:
    """Undo an apply that exported a now-cleared saved key.

    If ``GEMINI_API_KEY`` currently holds the cleared setting value, restore
    the env value this process first saw before applying a resolved key
    (shell env, or unset), so :func:`get_api_key` falls back env → baked.
    """
    if not cleared_key:
        return
    if os.environ.get("GEMINI_API_KEY") != cleared_key:
        return
    if _env_before_apply_set and _env_before_apply is not None:
        os.environ["GEMINI_API_KEY"] = _env_before_apply
    else:
        os.environ.pop("GEMINI_API_KEY", None)
