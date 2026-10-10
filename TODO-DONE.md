# TODO — Done

Finished items moved here from [TODO.md](TODO.md) once implementation and verification are complete.
Original wording kept; completion date added.

## Spec: Gemini 3.8 TTS backend migration (done 2026-10-10)

Verified: 31 mocked tests green (`pytest tests/ -q`); live smoke test on 3 Indonesian sentences
via `gemini-3.8-flash-lite-tts` — WAV probe `24000 1 2`, single RIFF header, `--style` run produces
distinct audio; `--list-voices --language id-ID` lists the voice library.

### Tasks

#### Phase 1 — Backend package

- [x] 1. `backends/base.py`: `TTSBackend` ABC — `synthesize_many(items, *, progress, cancel)`, `list_voices(language)`, plus `SynthesisRequest`/`SynthesisResult` dataclasses (text, voice, language, style → wav bytes or per-item error). (done 2026-10-10)
- [x] 2. `backends/gemini.py`: `genai.Client` from `GEMINI_API_KEY`; `models.generate_content` with `response_modalities=["AUDIO"]`, prebuilt voice config, `speech_metadata` style; unary WAV bytes written as-is; SDK errors mapped to per-item failures; both model IDs supported. Live fixes during implementation: `voices.list` takes flat kwargs (`language_code=[...]`), Voice `language_code` is a single string, server-side language filter unreliable → client-side match with full-list fallback, never iterate the response object. (done 2026-10-10)
- [x] 3. `backends/cloud_tts.py`: existing `synthesize_speech` logic (LINEAR16, 24 kHz) ported behind the ABC; language from `--language` or the voice-name prefix; raises on `style`. (done 2026-10-10)

#### Phase 2 — CLI

- [x] 4. `batch_generate_audio.py` rewritten: flags `--backend` (gemini|cloud-tts, default gemini), `--model`, `--voice` (default Kore / id-ID-Wavenet-A), `--language`, `--style`, `--list-voices`, `--force`, `--input`, `--output-dir`; `sentences.txt` → `output_audio/line_XXX.wav`, skip-existing, per-line progress, clean Ctrl-C (exit 130). (done 2026-10-10)
- [x] 5. `--list-voices` mode: fixed-width table (name/gender/languages/note); prints an auto-detect note when no voice is tagged for the requested language; works without an input file. (done 2026-10-10)

#### Phase 3 — Tests

- [x] 6. `tests/test_cli.py`: arg parsing, skip-existing/--force behavior, `--list-voices` path (mocked). (done 2026-10-10)
- [x] 7. `tests/test_gemini_backend.py`: request construction (modalities, voice, speech_metadata), WAV passthrough, error mapping (mocked genai client); plus regression tests for the live-found `list_voices` bugs. (done 2026-10-10)
- [x] 8. `tests/test_cloud_tts_backend.py`: request mapping, style rejection (mocked texttospeech client). (done 2026-10-10)

#### Phase 4 — Docs & verification

- [x] 9. `requirements.txt`: `google-genai>=2.25.0`, `google-cloud-texttospeech`, `python-dotenv`; `requirements-dev.txt` adds `pytest`; `.pytest_cache/` gitignored. (done 2026-10-10)
- [x] 10. `README.md` rewritten: `GEMINI_API_KEY` setup, new flags, voice discovery via `--list-voices`, multi-language notes, `--backend` switch with legacy Wavenet table. No `.env.example` shipped (matches repo history — it was deliberately removed before; README documents manual `.env` creation). (done 2026-10-10)
- [x] 11. Smoke test on 3 real sentences (`gemini-3.8-flash-lite-tts`, voice Kore, Indonesian auto-detected, no `--language`): probe `24000 1 2`, single RIFF header, `--style` sample differs. (done 2026-10-10)
- [x] 12. `pytest` green; committed per AGENTS.md convention; no credentials in `git show`. (done 2026-10-10)

### Definition of done

- [x] All 12 tasks above checked, each with its `Verify` step actually run.
- [x] `./venv/bin/python3 -m pytest tests/ -q` fully green (31 passed).
- [x] Smoke test probe prints `24000 1 2` and audio generates correctly.
- [x] `README.md` and `requirements.txt` match reality (AGENTS.md convention).
- [x] One clean commit (AGENTS.md convention); no credentials in `git show`.
- [x] Finished items moved here; only Follow-ups remain in TODO.md.

### Reference (kept for future debugging)

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | `ModuleNotFoundError: No module named 'google.generativeai'` | wrong (deprecated) package | install `google-genai`; import `from google import genai` |
| 2 | `TypeError/AttributeError` mentioning `response_format` | field exists only on Interactions API | delete it; unary default is already WAV |
| 3 | Audio file won't play / `wave.Error: unknown format` | WAV header double-wrapped | write API bytes raw; never use `wave.open` to write |
| 4 | `AttributeError: 'NoneType' object has no attribute 'data'` | text parts have `inline_data=None` | iterate `response.parts`, skip parts without inline data |
| 5 | Exception from `response.text` | audio-only response has no text | never call `.text`; walk `.parts` |
| 6 | Every line fails with auth error | invalid/missing `GEMINI_API_KEY` | treat 401/403/invalid-key as whole-run failure; print one clear error and exit 1 |
| 7 | Dict validation errors on request contents | snake_case vs camelCase confusion | Python SDK takes snake_case (`speech_metadata`, `inline_data`); camelCase is REST/JSONL-only (and Batch is out of scope) |
| 8 | `AttributeError` on `client.voices` | `google-genai` older than 2.25.0 | check the pin; raise a clear "upgrade google-genai" error |
| 9 | Model answers in English/reads style aloud | style leaked into text | verbatim transcript rule: style only in `speech_metadata` |
| 10 | `ValueError` on model name | stale tutorials suggest `gemini-2.5-flash-preview-tts`, `gemini-3.1-flash-tts-preview` | allowlist exactly the two `gemini-3.8-*-tts` IDs; error message lists valid ones |
| 11 | Agent builds `client.batches.create` flow | "batch" project name misread | forbidden by this spec — one sync `generate_content` per line |
| 12 | Ctrl-C leaves partial output | by design | catch `KeyboardInterrupt`, print summary, exit 130; skip-existing resumes later |
| 13 | `GOOGLE_API_KEY` shadows `GEMINI_API_KEY` | SDK precedence | documented: set only one; README says `GEMINI_API_KEY` |
| 14 | `429/RESOURCE_EXHAUSTED` on long lists | rate limiting | 3 retries with `2s/4s/8s` backoff per item, then per-item failure and continue |
| 15 | Filenames renumber when lines are skipped | index taken from pending list | always use the input line number for `line_{index:03d}.wav` |
| 16 | Tests hit the network | clients not injected | every backend takes `client=None` and tests pass `MagicMock()` |
| 17 | `Voices.list() got an unexpected keyword argument 'config'` | 2.29.0 takes flat filter kwargs | call `list_fn(language_code=[language])`, not `config={...}` |
| 18 | `--list-voices` prints `?` rows | iterated the response object instead of `.voices` | `entries = getattr(response, "voices", None) or []` — never fall back to `response` |
| 19 | Language filter returns nothing (e.g. no `id-ID`-tagged voices) | server-side filter unreliable / catalog gaps | client-side match + full-list fallback; prebuilt voices speak any supported language via auto-detect |
