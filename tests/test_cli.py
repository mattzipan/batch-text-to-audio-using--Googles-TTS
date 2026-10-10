"""CLI tests: parsing, validation, skip-existing, resume, list-voices."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import batch_generate_audio as cli
from helpers import FakeBackend


def _write_input(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_parser_defaults():
    args = cli.build_parser().parse_args([])
    assert args.backend == "gemini"
    assert args.model == "gemini-3.8-flash-lite-tts"
    assert args.voice is None
    assert args.language is None
    assert args.style is None
    assert args.list_voices is False
    assert args.force is False
    assert args.input == "sentences.txt"
    assert args.output_dir == "output_audio"


def test_resolve_voice_defaults():
    gemini_args = cli.build_parser().parse_args([])
    assert cli.resolve_voice(gemini_args) == "Kore"
    cloud_args = cli.build_parser().parse_args(["--backend", "cloud-tts"])
    assert cli.resolve_voice(cloud_args) == "id-ID-Wavenet-A"
    custom = cli.build_parser().parse_args(["--voice", "Aoede"])
    assert cli.resolve_voice(custom) == "Aoede"


def test_model_rejected_on_cloud_tts(monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_backend", lambda args: FakeBackend())
    code = cli.main(["--backend", "cloud-tts", "--model", "gemini-3.8-flash-tts"])
    assert code == 2
    assert "--model is gemini-only" in capsys.readouterr().err


def test_style_rejected_on_cloud_tts(monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_backend", lambda args: FakeBackend())
    code = cli.main(["--backend", "cloud-tts", "--style", "cheerful"])
    assert code == 2
    assert "--style is gemini-only" in capsys.readouterr().err


def test_missing_input_file(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "make_backend", lambda args: FakeBackend())
    code = cli.main(["--input", str(tmp_path / "nope.txt"),
                     "--output-dir", str(tmp_path / "out")])
    assert code == 1
    assert "not found" in capsys.readouterr().err


def test_backend_construction_failure(monkeypatch, capsys):
    def boom(args):
        raise RuntimeError("nope: bad credentials")

    monkeypatch.setattr(cli, "make_backend", boom)
    code = cli.main(["--list-voices"])
    assert code == 1
    assert "bad credentials" in capsys.readouterr().err


def test_skip_existing_and_numbering(monkeypatch, tmp_path, capsys):
    fake = FakeBackend()
    monkeypatch.setattr(cli, "make_backend", lambda args: fake)
    input_file = _write_input(tmp_path / "in.txt", ["satu", "dua", "tiga"])
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "line_001.wav").write_bytes(b"OLD")  # pre-existing: must be skipped

    code = cli.main(["--input", str(input_file), "--output-dir", str(out_dir)])
    assert code == 0
    # Backend saw only lines 2 and 3, with original 1-based indexes (no renumber).
    assert [i for i, _ in fake.received] == [2, 3]
    assert (out_dir / "line_001.wav").read_bytes() == b"OLD"
    assert (out_dir / "line_002.wav").read_bytes() == b"RIFF-fake"
    assert (out_dir / "line_003.wav").read_bytes() == b"RIFF-fake"
    assert "Skipping (1/3)" in capsys.readouterr().out


def test_force_regenerates_all(monkeypatch, tmp_path):
    fake = FakeBackend()
    monkeypatch.setattr(cli, "make_backend", lambda args: fake)
    input_file = _write_input(tmp_path / "in.txt", ["satu", "dua"])
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "line_001.wav").write_bytes(b"OLD")

    code = cli.main(["--input", str(input_file), "--output-dir", str(out_dir), "--force"])
    assert code == 0
    assert [i for i, _ in fake.received] == [1, 2]
    assert (out_dir / "line_001.wav").read_bytes() == b"RIFF-fake"


def test_request_fields_forwarded(monkeypatch, tmp_path):
    fake = FakeBackend()
    monkeypatch.setattr(cli, "make_backend", lambda args: fake)
    input_file = _write_input(tmp_path / "in.txt", ["halo"])
    out_dir = tmp_path / "out"

    code = cli.main(["--input", str(input_file), "--output-dir", str(out_dir),
                     "--voice", "Aoede", "--language", "id-ID", "--style", "warm"])
    assert code == 0
    assert len(fake.received) == 1
    _, req = fake.received[0]
    assert req.text == "halo"
    assert req.voice == "Aoede"
    assert req.language == "id-ID"
    assert req.style == "warm"


def test_per_item_failure_continues(monkeypatch, tmp_path, capsys):
    fake = FakeBackend(fail_indexes=(2,))
    monkeypatch.setattr(cli, "make_backend", lambda args: fake)
    input_file = _write_input(tmp_path / "in.txt", ["satu", "dua"])
    out_dir = tmp_path / "out"

    code = cli.main(["--input", str(input_file), "--output-dir", str(out_dir)])
    assert code == 0  # per-item failures do not fail the run
    assert (out_dir / "line_001.wav").exists()
    assert not (out_dir / "line_002.wav").exists()
    assert "Failed to generate line 2" in capsys.readouterr().err


def test_list_voices_needs_no_input(monkeypatch, tmp_path, capsys):
    fake = FakeBackend()
    monkeypatch.setattr(cli, "make_backend", lambda args: fake)
    code = cli.main(["--list-voices", "--input", str(tmp_path / "nope.txt")])
    assert code == 0
    out = capsys.readouterr().out
    assert "Zed" in out and "id-ID" in out


def test_keyboard_interrupt_exits_130(monkeypatch, tmp_path, capsys):
    fake = FakeBackend(interrupt_at=2)
    monkeypatch.setattr(cli, "make_backend", lambda args: fake)
    input_file = _write_input(tmp_path / "in.txt", ["satu", "dua", "tiga"])
    out_dir = tmp_path / "out"

    code = cli.main(["--input", str(input_file), "--output-dir", str(out_dir)])
    assert code == 130
    # Completed file stands; resume would pick up the rest.
    assert (out_dir / "line_001.wav").exists()
    assert not (out_dir / "line_002.wav").exists()
    assert "Cancelled" in capsys.readouterr().out


def test_empty_input_file(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "make_backend", lambda args: FakeBackend())
    input_file = _write_input(tmp_path / "in.txt", ["   ", ""])
    code = cli.main(["--input", str(input_file), "--output-dir", str(tmp_path / "o")])
    assert code == 1
    assert "no usable lines" in capsys.readouterr().err


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
