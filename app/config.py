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


def ensure_app_dirs() -> Path:
    """Create and return the per-user app data dir (~/.local/share/WordTape/)."""
    app_dir = Path.home() / ".local" / "share" / APP_NAME
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def apply_api_key_to_env() -> str:
    """Resolve the API key via get_api_key() and export it as GEMINI_API_KEY."""
    key: str = get_api_key()
    os.environ["GEMINI_API_KEY"] = key
    return key
