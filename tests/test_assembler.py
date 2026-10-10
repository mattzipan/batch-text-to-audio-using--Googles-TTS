"""Golden + edge-case tests for app.assembler (task B3).

Two synthetic 24 kHz mono 16-bit clips (0.5 s 440 Hz sine, 1.0 s
silence-as-audio) are written with stdlib ``wave`` into a scratch
project's audio cache; the ffmpeg step is mocked so only the argv is
asserted.
"""

from __future__ import annotations

import math
import struct
import subprocess
import wave
from pathlib import Path
from unittest import mock

import pytest

from app import assembler
from app.assembler import (
    WAV_PARAMS,
    build_track,
    estimate_duration,
    read_clip,
    silence,
)
from app.project import Project, audio_path, insert_row, new_project

SR = 24000
REPEATS = 5
REPEAT_GAP_S = 1.2
ITEM_GAP_S = 1.8
CLIP_A_S = 0.5
CLIP_B_S = 1.0


def _write_wav(
    path: Path,
    frames: bytes,
    framerate: int = SR,
    nchannels: int = 1,
    sampwidth: int = 2,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(nchannels)
        wav.setsampwidth(sampwidth)
        wav.setframerate(framerate)
        wav.writeframes(frames)
    return path


def _sine_frames(seconds: float, freq: float = 440.0, amp: int = 10000) -> bytes:
    n = round(SR * seconds)
    return b"".join(
        struct.pack("<h", int(amp * math.sin(2.0 * math.pi * freq * i / SR)))
        for i in range(n)
    )


@pytest.fixture
def project(tmp_path: Path) -> tuple[Project, list[tuple[str, str]], bytes, bytes]:
    """Scratch project with two cached clips; returns (project, ids, sine, zeros)."""
    proj = new_project(
        folder=tmp_path / "proj",
        source_lang="de",
        target_lang="id",
        variants_enabled=False,
    )
    proj.folder.mkdir(parents=True, exist_ok=True)
    (proj.folder / "audio").mkdir(exist_ok=True)
    row_a = insert_row(proj, None, "Guten Morgen", "Selamat pagi")
    row_b = insert_row(proj, None, "Danke", "Terima kasih")
    sine = _sine_frames(CLIP_A_S)
    zeros = b"\x00\x00" * round(SR * CLIP_B_S)
    _write_wav(audio_path(proj, row_a.id, row_a.variants[0].id), sine)
    _write_wav(audio_path(proj, row_b.id, row_b.variants[0].id), zeros)
    included = [
        (row_a.id, row_a.variants[0].id),
        (row_b.id, row_b.variants[0].id),
    ]
    return proj, included, sine, zeros


@pytest.fixture
def no_ffmpeg():
    with mock.patch.object(subprocess, "run") as run:
        yield run


def _expected_frames() -> int:
    clip_a = round(SR * CLIP_A_S)
    clip_b = round(SR * CLIP_B_S)
    gap = round(SR * REPEAT_GAP_S)
    item = round(SR * ITEM_GAP_S)
    per_a = REPEATS * clip_a + (REPEATS - 1) * gap + item
    per_b = REPEATS * clip_b + (REPEATS - 1) * gap + item
    return per_a + per_b - item  # trailing item_gap trimmed


def _read_output_frames(wav_path: str) -> tuple[tuple[int, int, int], bytes]:
    with wave.open(wav_path, "rb") as wav:
        params = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth())
        return params, wav.readframes(wav.getnframes())


def test_silence_is_zero_frames_int_math() -> None:
    gap = silence(REPEAT_GAP_S)
    assert gap == b"\x00" * round(SR * REPEAT_GAP_S) * 2
    assert len(gap) == 28800 * 2  # 1.2 s at 24 kHz, integer samples
    assert len(silence(ITEM_GAP_S)) == round(SR * ITEM_GAP_S) * 2


def test_build_track_golden_byte_length(
    project: tuple[Project, list[tuple[str, str]], bytes, bytes],
    no_ffmpeg: mock.MagicMock,
) -> None:
    proj, included, _, _ = project
    result = build_track(
        proj, included, repeats=REPEATS, repeat_gap_s=REPEAT_GAP_S, item_gap_s=ITEM_GAP_S
    )
    expected_frames = _expected_frames()
    assert result["wav"].endswith("output/final.wav")
    params, frames = _read_output_frames(str(result["wav"]))
    assert params == WAV_PARAMS
    assert len(frames) == expected_frames * 2
    with wave.open(str(result["wav"]), "rb") as wav:
        assert wav.getnframes() == expected_frames
    assert result["duration_s"] == pytest.approx(expected_frames / SR)


def test_layout_and_trailing_gap_trimmed(
    project: tuple[Project, list[tuple[str, str]], bytes, bytes],
    no_ffmpeg: mock.MagicMock,
) -> None:
    proj, included, sine, _ = project
    result = build_track(proj, included)
    _, frames = _read_output_frames(str(result["wav"]))
    clip_len = round(SR * CLIP_A_S) * 2
    gap_len = round(SR * REPEAT_GAP_S) * 2
    # Layout starts [clip][repeat_gap][clip]...
    assert frames[:clip_len] == sine
    assert frames[clip_len : clip_len + gap_len] == b"\x00" * gap_len
    assert frames[clip_len + gap_len : clip_len + gap_len + clip_len] == sine
    # Trailing item_gap absent: exact trimmed length, not one gap longer.
    expected_frames = _expected_frames()
    assert len(frames) == expected_frames * 2
    assert len(frames) != (expected_frames + round(SR * ITEM_GAP_S)) * 2


def test_params_mismatch_raises(
    project: tuple[Project, list[tuple[str, str]], bytes, bytes],
    no_ffmpeg: mock.MagicMock,
    tmp_path: Path,
) -> None:
    bad = tmp_path / "bad.wav"
    _write_wav(bad, _sine_frames(0.1), framerate=44100)
    with pytest.raises(ValueError, match="44100"):
        read_clip(bad)
    proj, included, _, _ = project
    row = insert_row(proj, None, "Hallo", "Halo")
    vid = row.variants[0].id
    _write_wav(audio_path(proj, row.id, vid), _sine_frames(0.1), framerate=44100)
    with pytest.raises(ValueError, match="44100"):
        build_track(proj, [(row.id, vid)])
    with pytest.raises(ValueError, match="44100"):
        estimate_duration(proj, [(row.id, vid)])


def test_missing_clip_raises(
    project: tuple[Project, list[tuple[str, str]], bytes, bytes],
    no_ffmpeg: mock.MagicMock,
) -> None:
    proj, _, _, _ = project
    with pytest.raises(FileNotFoundError):
        build_track(proj, [("nope01", "nope02")])
    with pytest.raises(FileNotFoundError):
        estimate_duration(proj, [("nope01", "nope02")])


def test_estimate_duration_matches_frame_math(
    project: tuple[Project, list[tuple[str, str]], bytes, bytes],
) -> None:
    proj, included, _, _ = project
    est = estimate_duration(
        proj, included, repeats=REPEATS, repeat_gap_s=REPEAT_GAP_S, item_gap_s=ITEM_GAP_S
    )
    assert est == pytest.approx(_expected_frames() / SR)
    assert estimate_duration(proj, []) == 0.0


def test_ffmpeg_argv_exact(
    project: tuple[Project, list[tuple[str, str]], bytes, bytes],
    no_ffmpeg: mock.MagicMock,
) -> None:
    proj, included, _, _ = project
    result = build_track(proj, included)
    assert no_ffmpeg.call_count == 1
    (argv,), kwargs = no_ffmpeg.call_args
    expected = [
        assembler._ffmpeg_exe(),
        "-y",
        "-i",
        str(result["wav"]),
        "-codec:a",
        "libmp3lame",
        "-b:a",
        "128k",
        str(result["mp3"]),
    ]
    assert argv == expected
    assert kwargs.get("check") is True
    assert kwargs.get("capture_output") is True


def test_ffmpeg_failure_raises_runtime_error(
    project: tuple[Project, list[tuple[str, str]], bytes, bytes],
) -> None:
    proj, included, _, _ = project
    err = subprocess.CalledProcessError(1, "ffmpeg", stderr=b"boom-tail")
    with mock.patch.object(subprocess, "run", side_effect=err):
        with pytest.raises(RuntimeError, match="boom-tail"):
            build_track(proj, included)
