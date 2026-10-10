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

## Spec: WordTape — executable UI (done 2026-10-10)

### Tasks

#### Phase A — Scaffold & data

- [x] A1. Create `app/` package skeleton (empty modules as in Architecture) + `app/config.py`
  with `APP_NAME = "WordTape"`, `TRANSLATION_MODEL = "gemini-3.5-flash-lite"`,
  `TTS_MODELS = ("gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts")`,
  `DEFAULT_VOICE = "Kore"`, `REPEATS, REPEAT_GAP_S, ITEM_GAP_S = 5, 1.2, 1.8`,
  `DEFAULT_SOURCE_LANG, DEFAULT_TARGET_LANG = "de", "id"`, and `resource_path(rel)`:
  returns `Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / rel` (PyInstaller-safe).
  API key resolution function `get_api_key()`: env `GEMINI_API_KEY` → else `secrets.API_KEY`
  → else raise with a clear message. Dev mode sets `os.environ["GEMINI_API_KEY"]` from it
  **before** any `genai.Client()` is constructed.
  **Watch out.** `import secrets` must be lazy/try-except — the file won't exist in dev.
  **Verify.** `./venv/bin/python3 -c "from app import config; print(config.APP_NAME)"`.

- [x] A2. `app/project.py`: dataclasses `Row`, `Variant`, `Project` with `load/save`
  (atomic `os.replace`), `new_project(folder, ...)`, and row ops:
  `insert_row(position, source, translation)`, `delete_row(id)`, `move_row(id, up|down)`,
  `update_variant_text(id, text)` (sets `status="stale"`), `mark_generating/ok/error`.
  Audio cache path: `audio/{row_id}_{variant_id}.wav`. `ensure_unique_ids()` on load.
  **Watch out.** Insert "at row N" = insert **before** current row N (1-based display);
  renumber `position` after every op; never renumber file names (ids are stable).
  **Verify.** `pytest tests/test_project.py` — roundtrip save/load, insert-before-N, delete,
  move boundaries (first/last), text-edit marks stale.

- [x] A3. Import parsing in `app/project.py` (or `app/importer.py` if it grows):
  `parse_txt(content) -> list[str]` (strip, skip empty); `parse_csv(content, has_header)`
  → `list[tuple[str, str]]`. Encoding `utf-8-sig` (BOM!), delimiter via `csv.Sniffer`
  with fallback: if parsing yields 1 column, retry with `;` then `\t` (European Excel!).
  **Watch out.** Danish/German Excel exports semicolon-separated CSVs with a UTF-8 BOM —
  both handled here; `csv.Sniffer` alone is unreliable on short files, hence manual retries.
  **Verify.** `pytest tests/test_project.py -k import` — includes a semicolon+BOM fixture.

#### Phase B — Services

- [x] B1. `app/translate.py`: `translate_rows(rows, source_lang, target_lang, with_variants)`
  using `google-genai` `client.models.generate_content(model=config.TRANSLATION_MODEL, ...)`
  with `response_mime_type="application/json"`. Batch **25 rows per call**. Prompt (keep
  close): *"Translate each source term from {source} into {target}. Return a JSON array of
  objects {source, translation, formal, informal}. translation = the most common everyday
  translation. formal/informal = alternatives with exactly the same meaning but more
  formal/informal register, or null if the language makes no such distinction. Never
  translate names."* Parse with `json.loads`; on failure, one retry asking for "ONLY valid
  JSON"; then per-batch error → rows `status="error"`.
  **Watch out.** Never set `temperature`/`top_p` (deprecated on 3.x — errors). Variants only
  requested when `with_variants` (else the fields must be omitted from the prompt to save
  tokens). Retries: 3 attempts with `2s/4s/8s` backoff on 429/5xx; auth errors abort the job.
  **Verify.** `pytest tests/test_translate.py` — mocked client: batching boundary at 25,
  JSON parse + parse-retry path, variants-off omits fields, 429 backoff, auth abort.

- [x] B2. `app/tts.py`: `generate_audio(project, variant_ids=None, force=False, progress,
  cancel)` — wraps `backends.gemini.GeminiBackend` (`synthesize_many` already yields
  progress/cancel). Writes WAVs to the cache path; sets per-variant status. `test_voice(
  voice, model, text) -> bytes` (one-off). `list_voices(model, language)` delegates to
  `backends`. Language passed via `SynthesisRequest.language` for lookup only (TTS
  auto-detects the text).
  **Watch out.** Skip `status=="ok"` unless `force` or `status=="stale"`; build the request
  list with the **stable variant ids** in `index` field so results map back correctly.
  **Verify.** `pytest tests/test_tts.py` with a FakeBackend: stale-only regeneration, force,
  cache file naming, progress callback counts.

- [x] B3. `app/assembler.py`: `build_track(project, included_variant_ids) -> (wav_path,
  mp3_path, duration_s)`. Pure Python with stdlib `wave`: assert every clip is
  (24000, 1, 2) — raise a clear error otherwise; silence = `b"\x00\x00" * round(24000*s)`.
  Layout per item (5 plays, gaps after plays 1–4 = `repeat_gap_s`, after play 5 =
  `item_gap_s`; **trim the trailing `item_gap_s`** after the final item):

  ```
  [clip][1.2s][clip][1.2s][clip][1.2s][clip][1.2s][clip][1.8s] [clip]...
  |________________ 5x per translation ________________|
  ```

  Then MP3 via ffmpeg: `ffmpeg -y -i final.wav -codec:a libmp3lame -b:a 128k final.mp3`
  (binary: `app/ffmpeg_bin/ffmpeg` if present else `imageio_ffmpeg.get_ffmpeg_exe()`;
  `subprocess.run(..., check=True, capture_output=True)`; on failure raise with stderr).
  Output: `output/final.wav` + `output/final.mp3` + duration for the UI.
  **Watch out.** Keep WAV math in samples/frames (ints) — never float byte offsets;1.2 s
  at 24 kHz = 28800 samples = 57600 bytes. Verify the round-trip with a golden test.
  **Verify.** `pytest tests/test_assembler.py` — two synthetic clips → exact output byte
  length, trailing gap trimmed, params mismatch raises, duration formula matches bytes.

- [x] B4. Job manager `app/jobs.py`: `start(kind, fn) -> job_id`, `get(job_id)`,
  `cancel(job_id)`, `Job` dataclass as described in the API surface. One active job (409).
  **Verify.** `pytest tests/test_server.py::test_jobs` — progress visible, cancel stops.

#### Phase C — Server

- [x] C1. `app/server.py`: FastAPI app implementing **every route in the API surface table**
  exactly (paths, verbs, payload keys). `StaticFiles` for `/static`, `FileResponse` for
  `/media/*` with a path-traversal guard (resolve + must stay under the project folder).
  Frontend served at `/` (index.html). CORS not needed (same origin).
  **Watch out.** `/media` must `Path.resolve()` and check `is_relative_to(project_root)` —
  classic traversal hole otherwise. Jobs run in threads; FastAPI sync `def` endpoints are
  fine (threadpool).
  **Verify.** `pytest tests/test_server.py` — `TestClient` exercises every route with mocked
  services; includes traversal-attempt test (`../../etc/passwd` → 404).

- [x] C2. Free-port + server boot helper: bind `('127.0.0.1', 0)` to find a port, pass to
  `uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=p, workers=1, log_level="warning"))`
  in a daemon thread; `wait_until_up(url, timeout=10)` via `urllib` poll.
  **Watch out.** Never `uvicorn.run` and never `reload`/`workers>1` — subprocess spawning
  breaks PyInstaller. Call `multiprocessing.freeze_support()` in `main()` first line.
  **Verify.** Manual: `./venv/bin/python3 -m app.main --server-only` serves on the printed
  URL and `curl` works (add that flag while developing).

#### Phase D — Frontend

- [x] D1. `app/frontend/styles.css`: design tokens block **verbatim from the design brief**,
  then all component classes listed there, motion keyframes, focus-visible styles. Fonts:
  download Fraunces (400, 600, italic) + Karla (400, 500, 700) woff2 (latin subset) from
  Google Fonts, commit into `app/frontend/fonts/`, `@font-face` with local fallbacks.
  **Watch out.** One CSS file only; no preprocessors; no external CDN at runtime.
  **Verify.** Open `index.html` in a browser (even file://) — tokens render, buttons show
  `--shadow-pop`, fonts load or fall back gracefully.

- [x] D2. `app/frontend/index.html` + `app.js`: the three screens exactly as in the design
  brief (Word / Voice / Bake), stepper, toasts, modal. `app.js` (~600 lines, vanilla):
  `state` object synced from `GET /api/state`; `render()` re-renders each screen's dynamic
  parts (rows table, voice select, inclusion list, estimate); `api(path, opts)` fetch
  wrapper with error→toast; `poll(jobId, onDone)` at 500 ms; file drop + input for import;
  `<audio>` playback of `/media/...` URLs and test-voice blob URLs.
  **Watch out.** All user-visible strings **verbatim from the microcopy list**. Number inputs
  send floats for gaps (`1.2` not `1`). Disable Generate/Bake buttons while a job runs.
  **Verify.** Run with `--server-only`, drive all three screens against a 5-row demo project
  with services mocked behind the real server; every flow reachable by click only.

- [x] D3. Post-processing completeness on the Words screen (the user's open question —
  this is the answer): edit translation text (marks `stale` + toast *"Row {n} is stale —
  regenerate it."*), `↻ Regenerate` per variant, `+ Below` insert after row N, bottom
  "Add at the end" + "Add at row #N" forms, `↑/↓` reorder, `✕` delete (modal confirm),
  and **rebuild is instant/local** (Bake screen rebuild from cache). Recent projects list
  on Words screen when no project is open (folder paths from a tiny `recent.json` in the
  app data dir `~/.local/share/WordTape/`).
  **Verify.** Manual walkthrough: change one word → regenerate → rebuild; insert at row 3;
  delete row; reorder; close app; reopen project — all state intact.

#### Phase E — Desktop shell

- [x] E1. `app/main.py`: `if __name__ == "__main__": multiprocessing.freeze_support(); main()`.
  `main()`: resolve key → start server thread (C2) → try `import webview` and
  `webview.create_window(APP_NAME, url, width=1280, height=800, min_size=(1024, 700),
  js_api=Api())` → `webview.start()`; on **any** webview exception: print a one-line hint
  and `webbrowser.open(url)` then keep the server thread alive (join with a "Ctrl-C to quit"
  message). `Api` class: `pick_folder()`, `pick_file(extensions)` via
  `webview.windows[0].create_file_dialog(...)` (used by Words screen when choosing project
  folders; the UI falls back to a typed path input if these return None).
  `--server-only` flag: no window, just print the URL (used for development).
  **Watch out.** `js_api` methods are called from JS asynchronously — return plain JSON-safe
  values (str/list/None). Import webview **inside** `main()` so the fallback works even
  when pywebview is absent from the build.
  **Verify.** `./venv/bin/python3 -m app.main` opens a native window on this Mint machine;
  `--server-only` prints a working URL.

#### Phase F — Packaging

- [x] F1. `build.sh`: (1) `./venv/bin/pip install -r requirements-dev.txt`; (2) fonts check
  (fail with message if `frontend/fonts/*.woff2` missing); (3) copy ffmpeg binary:
  `python -c "import imageio_ffmpeg, shutil, pathlib; shutil.copy(imageio_ffmpeg.get_ffmpeg_exe(),
  'app/ffmpeg_bin/ffmpeg')"`; (4) generate `app/secrets.py` from `.env`
  (`API_KEY = "..."` — read with python-dotenv; fail loudly if unset); (5) run PyInstaller:
  `./venv/bin/pyinstaller --onefile --name WordTape --add-data app/frontend:app/frontend
  --add-binary app/ffmpeg_bin/ffmpeg:app/ffmpeg_bin --hidden-import webview.platforms.gtk
  --collect-all webview --collect-all httpx --collect-all google.genai app/main.py`;
  (6) `dist/WordTape` exists and `--help` runs. Add `app/secrets.py`, `app/ffmpeg_bin/`,
  `dist/`, `build/`, `projects/`, `*.spec` to `.gitignore` (keep `build.sh`).
  **Watch out.** PyGObject/`gi` must **not** be bundled — it comes from the system (Trap 1).
  The venv used for building should be created with `--system-site-packages` so `gi` is
  importable; document this in README. `--collect-all` on `google.genai`/`httpx` is needed
  because google-genai lazy-imports submodules PyInstaller misses.
  **Verify.** Run `./dist/WordTape` **outside** the venv on this machine → full smoke:
  import 5 words, translate, test voice, generate, bake, play MP3.

- [x] F2. `build-docker.sh` (glibc fallback, Trap 2): same build inside
  `docker run --rm -v "$PWD":/src -w /src ubuntu:22.04` after
  `apt-get update && apt-get install -y python3 python3-venv python3-gi python3-gi-cairo
  gir1.2-webkit2-4.0 build-essential` + pip installs. Produces a glibc-2.35-linked binary
  that runs on older Zorin. Only needed if the Mint-built binary fails on Zorin.
  **Verify.** Script runs to `dist/WordTape` in the container (or document as untested
  fallback with exact commands if docker is unavailable — checked at execution time).

- [x] F3. Key-in security note (one paragraph in README): the binary contains the Gemini
  API key and is recoverable with `strings`; acceptable for personal two-user use; do not
  upload the binary to public scanners/sharing; rotate the key in AI Studio if leaked;
  env var `GEMINI_API_KEY` overrides the baked key (useful after rotation).

#### Phase G — Docs & verification

- [x] G1. README section **WordTape (desktop app)**: what it is, run from source
  (`./venv/bin/python3 -m app.main`), build (`./build.sh`), Zorin note (copy `dist/WordTape`;
  if `GLIBC_x.y not found` → `./build-docker.sh`), first-run flow (new project → import),
  screenshots optional. Update `requirements.txt`: add `fastapi`, `uvicorn`, `pywebview`,
  `imageio-ffmpeg`; `requirements-dev.txt` adds `pyinstaller`. Sync `AGENTS.md` (app layout
  + "no build step in frontend" + secrets convention).
  **Verify.** README commands all run as written.

- [x] G2. Full end-to-end on the built binary (the real acceptance test):
  1. New project (de→id, variants ON). 2. Import a 10-word German `.txt`. 3. Translate →
  10 rows × up to 3 variants. 4. Test two voices. 5. Generate all (progress + cancel once,
  then resume). 6. Edit one translation → regenerate that one. 7. Insert a row at position 3
  and one at the end; delete one; reorder one. 8. Bake with defaults → estimate ≈ sum of
  clips×5 + gaps; play final.mp3: each translation 5× with audible repeat breaks, **no
  German in the track**. 9. Copy MP3 to a phone and confirm playback. 10. Close/reopen the
  project — everything persists.
  **Verify.** All 10 steps pass on Mint; user repeats steps 1–3 and 8 on Zorin.

- [x] G3. `pytest tests/ -q` fully green; commit everything (message like
  `Add WordTape desktop app (pywebview + FastAPI) on executable-ui`); move finished items to
  `TODO-DONE.md`.

### Definition of done

- [x] All tasks A1–G3 checked with their `Verify` steps actually run.
- [x] `pytest tests/ -q` green; `./dist/WordTape` passes the 10-step acceptance walk (G2).
- [x] Binary runs on Linux Mint (this machine) and is handed to the user for a Zorin check.
- [x] README/requirements/AGENTS.md in sync (repo convention); one clean commit on
  `executable-ui`; no secrets in `git show`.
- [x] Finished items moved to `TODO-DONE.md`.
