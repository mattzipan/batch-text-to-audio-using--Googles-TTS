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
    """Return the Gemini API key from env GEMINI_API_KEY or app/secrets.py.

    Raises:
        RuntimeError: If neither source provides a non-empty key.
    """
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
        "Gemini API key not found. Set the GEMINI_API_KEY environment variable "
        "or copy app/secrets.example.py to app/secrets.py and set API_KEY there."
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


def export_dir(project_name: str) -> Path:
    """Final track destination: ~/Music/WordTape/<project>/, else <app>/output/<project>/.

    WORDTAPE_EXPORT_DIR overrides both (used by tests and as an escape hatch).
    """
    env = os.environ.get("WORDTAPE_EXPORT_DIR")
    if env:
        root = Path(env)
    else:
        music = music_dir()
        root = (music / APP_NAME) if music else (app_root() / "output")
    return root / project_name


def apply_api_key_to_env() -> str:
    """Resolve the API key via get_api_key() and export it as GEMINI_API_KEY."""
    key: str = get_api_key()
    os.environ["GEMINI_API_KEY"] = key
    return key
