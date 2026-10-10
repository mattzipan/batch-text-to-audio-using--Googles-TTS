"""Batch text-to-audio generator.

Reads one sentence per line from --input and writes one .wav per line to
--output-dir as line_001.wav, line_002.wav, ... (1-based, zero-padded).

Backends (see backends/): gemini (default) or cloud-tts.
"""

import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from backends.base import SynthesisRequest, TTSBackend
from backends.cloud_tts import DEFAULT_VOICE as CLOUD_TTS_DEFAULT_VOICE
from backends.cloud_tts import CloudTTSBackend
from backends.gemini import DEFAULT_MODEL, DEFAULT_VOICE, VALID_MODELS, GeminiBackend

INPUT_FILE = "sentences.txt"
OUTPUT_DIR = "output_audio"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate audio files from a line-per-sentence text file."
    )
    parser.add_argument(
        "--backend",
        choices=("gemini", "cloud-tts"),
        default="gemini",
        help="TTS backend to use (default: gemini)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Gemini model (default: {DEFAULT_MODEL}). "
        f"Valid: {', '.join(VALID_MODELS)}. Gemini backend only.",
    )
    parser.add_argument(
        "--voice",
        default=None,
        help=f"Voice name (default: {DEFAULT_VOICE} for gemini, "
        f"{CLOUD_TTS_DEFAULT_VOICE} for cloud-tts). "
        "Use --list-voices to discover voices.",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="BCP-47 language code (e.g. id-ID). Optional for gemini "
        "(language is auto-detected); used for voice lookup/validation.",
    )
    parser.add_argument(
        "--style",
        default=None,
        help="Delivery style for gemini (e.g. 'warm and friendly'). "
        "Not supported by cloud-tts.",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List available voices (optionally filtered by --language) and exit.",
    )
    parser.add_argument(
        "--input", default=INPUT_FILE, help=f"Input text file (default: {INPUT_FILE})"
    )
    parser.add_argument(
        "--output-dir", default=OUTPUT_DIR, help=f"Output directory (default: {OUTPUT_DIR})"
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing audio files"
    )
    return parser


def make_backend(args: argparse.Namespace) -> TTSBackend:
    if args.backend == "gemini":
        return GeminiBackend(model=args.model)
    return CloudTTSBackend()


def resolve_voice(args: argparse.Namespace) -> str:
    if args.voice:
        return args.voice
    return DEFAULT_VOICE if args.backend == "gemini" else CLOUD_TTS_DEFAULT_VOICE


def print_voices(backend: TTSBackend, language: str | None) -> None:
    voices = backend.list_voices(language)
    if language and not any(
        language.lower() in (lc.lower() for lc in v.languages) for v in voices
    ):
        print(f"(no voices tagged for {language}; prebuilt voices speak it "
              f"via auto-detect — showing all)")
    print(f"{'NAME':<22}{'GENDER':<10}{'LANGUAGES':<40}NOTE")
    for v in voices:
        langs = ", ".join(v.languages[:5])
        if len(v.languages) > 5:
            langs += ", ..."
        print(f"{v.name:<22}{v.gender or '-':<10}{langs:<40}{v.note or '-'}")


def run(args: argparse.Namespace) -> int:
    if args.backend == "cloud-tts" and args.model != DEFAULT_MODEL:
        print(f"Error: --model is gemini-only, not valid with --backend cloud-tts.",
              file=sys.stderr)
        return 2
    if args.backend == "cloud-tts" and args.style:
        print("Error: --style is gemini-only, not valid with --backend cloud-tts.",
              file=sys.stderr)
        return 2

    try:
        backend = make_backend(args)
    except Exception as e:  # missing credentials, bad model, ...
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.list_voices:
        try:
            print_voices(backend, args.language)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        return 0

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: {args.input} not found.", file=sys.stderr)
        return 1
    with open(input_path, encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    if not lines:
        print(f"Error: {args.input} contains no usable lines.", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    voice = resolve_voice(args)
    # Skip-existing is computed BEFORE any API call: never pay for skipped lines.
    # Indexing is 1-based from the input line number — skips never renumber.
    items: list[tuple[int, SynthesisRequest]] = []
    for i, text in enumerate(lines, start=1):
        output_path = output_dir / f"line_{i:03d}.wav"
        if output_path.exists() and not args.force:
            print(f"Skipping ({i}/{len(lines)}): {text[:30]}... (File already exists)")
            continue
        items.append(
            (i, SynthesisRequest(text=text, voice=voice,
                                 language=args.language, style=args.style))
        )

    print(f"Found {len(lines)} lines ({len(items)} to generate). "
          f"Backend: '{args.backend}', voice: '{voice}'.")
    print("Starting generation...")

    start_time = time.time()
    success_count = 0
    failure_count = 0
    cancelled = False
    try:
        for result in backend.synthesize_many(
            items, progress=None, cancel=lambda: cancelled
        ):
            text = lines[result.index - 1]
            if result.ok:
                assert result.audio is not None
                # WAV bytes are written as-is: Gemini unary output and Cloud TTS
                # LINEAR16 both already contain a RIFF header. Never re-wrap.
                (output_dir / f"line_{result.index:03d}.wav").write_bytes(result.audio)
                print(f"Generated ({result.index}/{len(lines)}): {text[:30]}...")
                success_count += 1
            else:
                print(f"Failed to generate line {result.index}: {result.error}",
                      file=sys.stderr)
                failure_count += 1
    except KeyboardInterrupt:
        cancelled = True
        print("\nCancelled. Re-run to resume (existing files are skipped).")
        return 130
    except Exception as e:  # whole-run failure (auth, ...)
        print(f"Error: {e}", file=sys.stderr)
        return 1

    duration = time.time() - start_time
    print("\nBatch processing complete.")
    print(f"Successfully generated {success_count} files "
          f"({failure_count} failed) in {duration:.2f} seconds.")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()  # reads .env if present; never overrides existing env vars
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
