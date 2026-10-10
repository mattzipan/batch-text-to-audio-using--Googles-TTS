# AGENTS.md — Project Instructions

## What this project is

A batch text-to-audio generator: reads a line-per-sentence text file (`sentences.txt`) and writes
one `.wav` per line to `output_audio/`. Originally an Indonesian-only Google Cloud TTS tool
(Wavenet voices); currently migrating to **Gemini 3.8 TTS** (see `TODO.md`).

**Product direction: multi-language.** Indonesian-first defaults are fine; never hardcode `id-ID`
or any language-specific assumptions into the code.

## Stack

- Python 3.12+
- `google-genai>=2.25.0` — Gemini backend (auth: `GEMINI_API_KEY` env var, `GOOGLE_API_KEY` also works)
- `google-cloud-texttospeech` — optional Cloud TTS fallback backend (auth: `service-account.json`)
- `pytest` — tests with mocked API clients
- `fastapi` + `uvicorn` — WordTape local server; `pywebview` — native window;
  `imageio-ffmpeg` — static ffmpeg binary source (build time)

## Layout

- `batch_generate_audio.py` — CLI entry point
- `backends/` — `base.py` (`TTSBackend` ABC + request/result dataclasses), `gemini.py`, `cloud_tts.py`
- `sentences.txt` — input, one sentence per line, UTF-8
- `output_audio/line_XXX.wav` — output, 24 kHz mono 16-bit WAV
- `app/` — WordTape desktop app: `main.py` (webview shell + browser fallback),
  `server.py` (FastAPI), `project.py` (project.json + row ops), `translate.py`
  (`gemini-3.5-flash-lite`), `tts.py` (wraps `backends/`), `assembler.py` (pure-Python
  WAV concat), `jobs.py`, `boot.py`, `config.py`, `frontend/` (vanilla HTML/CSS/JS,
  no build step), `ffmpeg_bin/` (gitignored, build-time copy)
- `build.sh` — onefile PyInstaller build (bakes `.env` key into `app/secrets.py`,
  gitignored); `build-docker.sh` — glibc fallback build (untested)
- `tests/` — mocked unit tests (CLI + app)
- `TODO.md` / `TODO-DONE.md` — the tracker (see Workflow)

## Gemini TTS facts (3.8)

- Models: `gemini-3.8-flash-lite-tts` (default, cheap workhorse) and `gemini-3.8-flash-tts` (flagship quality).
- Synchronous `models.generate_content` path only for now. Batch API is deliberately deferred (no official TTS-in-batch example; see `TODO.md` Follow-ups).
- Input text is a **verbatim transcript**. Delivery style goes in `speech_metadata` (`--style`); inline `<laugh>`, `<sigh>`, `<short pause>` tags are spoken events and pass through in the text.
- Default voice `Kore`; discovery via `client.voices.list(language_code=...)` (`--list-voices`). No published voice→language map.
- Unary output is already a complete WAV (24 kHz mono 16-bit LE). Write bytes as-is — do **not** wrap with a manual RIFF header.
- Language is auto-detected from the text; `--language` (BCP-47) is optional and used for voice lookup/validation.

## Conventions

- **Git:** commit code changes after successful implementation and verification.
- **Docs/dep sync:** keep `README.md` and `requirements.txt` up to date with any code changes.
- **Credentials:** `service-account.json` and `.env` are gitignored. Never commit secrets or API keys. Exception: `build.sh` bakes `.env`'s key into `app/secrets.py` (gitignored) for the personal-use binary only.
- **Backend boundary:** both backends implement the `TTSBackend` ABC with `synthesize_many(items, *, progress, cancel)`. WordTape (`app/tts.py`) imports `backends/` directly — keep this boundary stable (progress callback + cancel check included).
- **Frontend:** plain HTML/CSS/JS, no build step. Design tokens live in `app/frontend/styles.css`; user-visible strings follow the microcopy list in the WordTape spec (`TODO-DONE.md`).
- **Output contract:** files are `output_audio/line_XXX.wav` (24 kHz mono 16-bit WAV); existing files are skipped unless `--force`.

## WordTape interface (built 2026-10-10, see `IDEA.md` for the original options)

WordTape is the desktop interface (2 users): pywebview native window over a local
FastAPI server, JSON project files in `~/WordTape/projects/`, PyInstaller onefile
(`dist/WordTape`, built on Mint, runs on Zorin 18). Implications that remain in force:

- `backends/` must stay importable as a plain library — no CLI imports, no global state, no
  prints inside the backends package.
- Keep the `synthesize_many(items, progress, cancel)` boundary stable: progress and cancel are
  how the UI drives a run.
- Avoid server-side or environment-specific assumptions in the backend layer.
- App modules import `backends` lazily/inside functions where possible so `import app.x`
  never requires credentials or a display.

## Workflow

- Plans and specs live in `TODO.md` under `## Spec: <feature>` headings. Never overwrite or renumber existing items.
- When a task is finished and verified, move it to `TODO-DONE.md` (keep its original wording, add the date).
