"""WordTape track assembler: concat cached clips into a drill tape.

Layout per included item (``repeats`` plays, default 5)::

    [clip][repeat_gap] ... [clip][repeat_gap][clip][item_gap]
    |________________ repeats x per item ________________|

i.e. ``repeat_gap_s`` after plays 1..repeats-1, ``item_gap_s`` after the
final play of each item — then the trailing ``item_gap_s`` after the
final item is trimmed.

All sample math stays in integer frames; silence is zero frames
(``b"\\x00\\x00"`` per mono 16-bit sample). Concatenation uses stdlib
:mod:`wave` only and streams to disk (never holds the track in RAM).
"""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path

from app.project import Project, audio_path

WAV_PARAMS: tuple[int, int, int] = (24000, 1, 2)  # (framerate, nchannels, sampwidth)
FRAMERATE, NCHANNELS, SAMPWIDTH = WAV_PARAMS


def _params_of(path: str | Path) -> tuple[int, int, int, int]:
    """Return (framerate, nchannels, sampwidth, nframes) for a WAV file."""
    with wave.open(str(path), "rb") as wav:
        return (
            wav.getframerate(),
            wav.getnchannels(),
            wav.getsampwidth(),
            wav.getnframes(),
        )


def _clip_path(project: Project, row_id: str, variant_id: str) -> Path:
    path = audio_path(project, row_id, variant_id)
    if not path.is_file():
        raise FileNotFoundError(f"missing audio clip: {path}")
    return path


def read_clip(path: str | Path) -> bytes:
    """Return the raw audio frames of a cached clip (no WAV header).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If its (framerate, nchannels, sampwidth) != WAV_PARAMS.
    """
    framerate, nchannels, sampwidth, _ = _params_of(path)
    actual = (framerate, nchannels, sampwidth)
    if actual != WAV_PARAMS:
        raise ValueError(
            f"{path}: expected WAV params (framerate, nchannels, sampwidth)"
            f" {WAV_PARAMS}, got {actual}"
        )
    with wave.open(str(path), "rb") as wav:
        return wav.readframes(wav.getnframes())


def silence(seconds: float) -> bytes:
    """Return ``seconds`` of silence as mono 16-bit zero frames."""
    return b"\x00\x00" * round(FRAMERATE * seconds)


def _gap_frames(seconds: float) -> int:
    return round(FRAMERATE * seconds)


def estimate_duration(
    project: Project,
    included: list[tuple[str, str]],
    repeats: int = 5,
    repeat_gap_s: float = 1.2,
    item_gap_s: float = 1.8,
) -> float:
    """Estimate the final track duration in seconds.

    Per item: ``repeats * clip_s + (repeats - 1) * repeat_gap_s +
    item_gap_s``, minus one trailing ``item_gap_s`` (trimmed from the
    final track). Clip lengths come from the cached WAV headers.

    Raises:
        FileNotFoundError: If a cached clip is missing.
        ValueError: If a cached clip has unexpected WAV params.
    """
    if not included:
        return 0.0
    total_s = 0.0
    for row_id, variant_id in included:
        path = _clip_path(project, row_id, variant_id)
        # Validate params so the estimate never silently accepts a bad clip.
        framerate, nchannels, sampwidth, nframes = _params_of(path)
        if (framerate, nchannels, sampwidth) != WAV_PARAMS:
            raise ValueError(
                f"{path}: expected WAV params (framerate, nchannels,"
                f" sampwidth) {WAV_PARAMS}, got {(framerate, nchannels, sampwidth)}"
            )
        clip_s = nframes / FRAMERATE
        total_s += repeats * clip_s + (repeats - 1) * repeat_gap_s + item_gap_s
    return total_s - item_gap_s


def _ffmpeg_exe() -> str:
    bundled = Path(__file__).resolve().parent / "ffmpeg_bin" / "ffmpeg"
    if bundled.is_file():
        return str(bundled)
    from imageio_ffmpeg import get_ffmpeg_exe

    return str(get_ffmpeg_exe())


def build_track(
    project: Project,
    included: list[tuple[str, str]],
    repeats: int = 5,
    repeat_gap_s: float = 1.2,
    item_gap_s: float = 1.8,
) -> dict[str, object]:
    """Assemble the drill tape and encode MP3.

    Writes ``output/final.wav`` (streamed, incremental frames) then
    ``output/final.mp3`` via bundled ffmpeg (libmp3lame, 128k).

    Returns:
        ``{"wav": str, "mp3": str, "duration_s": float}``.

    Raises:
        FileNotFoundError: If a cached clip is missing.
        ValueError: If a clip's WAV params mismatch or repeats < 1.
        RuntimeError: If the ffmpeg encode step fails (stderr tail).
    """
    if repeats < 1:
        raise ValueError(f"repeats must be >= 1, got {repeats!r}")
    repeat_gap = silence(repeat_gap_s)
    item_gap = silence(item_gap_s)
    repeat_gap_frames = _gap_frames(repeat_gap_s)
    item_gap_frames = _gap_frames(item_gap_s)

    out_dir = project.folder / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / "final.wav"
    mp3_path = out_dir / "final.mp3"

    total_frames = 0
    last_index = len(included) - 1
    with wave.open(str(wav_path), "wb") as out:
        out.setnchannels(NCHANNELS)
        out.setsampwidth(SAMPWIDTH)
        out.setframerate(FRAMERATE)
        for index, (row_id, variant_id) in enumerate(included):
            clip_path = _clip_path(project, row_id, variant_id)
            clip = read_clip(clip_path)
            clip_frames = len(clip) // SAMPWIDTH
            for play in range(repeats):
                out.writeframes(clip)
                total_frames += clip_frames
                if play < repeats - 1:
                    out.writeframes(repeat_gap)
                    total_frames += repeat_gap_frames
            if index < last_index:
                out.writeframes(item_gap)
                total_frames += item_gap_frames
    duration_s = total_frames / FRAMERATE

    ffmpeg = _ffmpeg_exe()
    argv = [
        ffmpeg,
        "-y",
        "-i",
        str(wav_path),
        "-codec:a",
        "libmp3lame",
        "-b:a",
        "128k",
        str(mp3_path),
    ]
    try:
        subprocess.run(argv, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        raw = exc.stderr
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        raise RuntimeError(f"ffmpeg encode failed for {wav_path}: {text[-2000:]}") from exc

    return {"wav": str(wav_path), "mp3": str(mp3_path), "duration_s": duration_s}
