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

## Layout

- `batch_generate_audio.py` — CLI entry point
- `backends/` — `base.py` (`TTSBackend` ABC + request/result dataclasses), `gemini.py`, `cloud_tts.py`
- `sentences.txt` — input, one sentence per line, UTF-8
- `output_audio/line_XXX.wav` — output, 24 kHz mono 16-bit WAV
- `tests/` — mocked unit tests
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
- **Credentials:** `service-account.json` and `.env` are gitignored. Never commit secrets or API keys.
- **Backend boundary:** both backends implement the `TTSBackend` ABC with `synthesize_many(items, *, progress, cancel)`. The future interface will import `backends/` directly — keep this boundary stable (progress callback + cancel check included).
- **Output contract:** files are `output_audio/line_XXX.wav` (24 kHz mono 16-bit WAV); existing files are skipped unless `--force`.

## Future interface (see `IDEA.md`)

The next phase is a small interface for 2–3 users, with deployment options sketched in `IDEA.md`
(SQLite storage; either a PyInstaller-packaged desktop app with a local FastAPI/browser window, or
static Astro + serverless API, or pure static with browser-local data). Implications for today's
code:

- `backends/` must stay importable as a plain library — no CLI imports, no global state, no
  prints inside the backends package.
- Keep the `synthesize_many(items, progress, cancel)` boundary stable: progress and cancel are
  how the UI will drive a run.
- Avoid server-side or environment-specific assumptions in the backend layer.

## Workflow

- Plans and specs live in `TODO.md` under `## Spec: <feature>` headings. Never overwrite or renumber existing items.
- When a task is finished and verified, move it to `TODO-DONE.md` (keep its original wording, add the date).
