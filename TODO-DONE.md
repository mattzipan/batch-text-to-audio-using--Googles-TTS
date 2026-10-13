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

---

## Spec: WordTape fixes batch 2 — UX polish, settings, layout (done 2026-10-11)

Status: **complete (2026-10-11)**. All 10 sub-specs implemented and verified
(183 mocked tests green; browser click-through: choice cards, toasts, clickable
switches, pending/generating chips, Settings screen, tiling at 700px; PATCH/404/
masking checks via curl). Originally: 10 sub-specs (F1–F10) covering 11 user items
(toggles merged into one root-cause fix; API key + output folder share one
Settings screen but are separate tasks). Each sub-spec is self-contained and
ordered by dependency — a junior agent can execute any single one alone.
General rules for all: frontend is plain HTML/CSS/JS, no build step; pytest
with mocked clients; never commit `app/secrets.py`, `.env`, `dist/`, `build/`.

### F1 — Success toast on new project (naming: "toast")

Goal: after creating a project, show a success toast — the same component used
for the name-validation warning.

Confirmed naming for future reference: **toast**. Component = `#toasts`
container (`app/frontend/index.html:182`) + `toast(message)` fn
(`app/frontend/app.js:17-24`) + `.toast` class (`app/frontend/styles.css:292-306`).
Validation warnings today are server 400/409 details surfaced via `api()`
(`app.js:43-44`); there is no success call in `doNew()` (`app.js:691-707`).

Files: `app/frontend/app.js` only (no server change).

Steps:
1. In `doNew()`, after `await refreshVoices();` (`app.js:706`), add:
   `toast("Created project " + data.project.name + ".");`
   Use the already-returned `data.project.name` (server `state_payload()` needs
   no change).
2. Do NOT add an "opened" toast in `doOpen()` (out of scope — keeps this diff
   to one line).
3. Keep microcopy verbatim: `Created project {name}.` (matches existing
   `Imported {n} rows.` / `Translated {n} rows.` pattern).

Verify: `./venv/bin/python3 -m app.main --server-only`, create project with a
valid name → toast appears bottom-center, auto-hides ~3.5 s; invalid name still
shows the server-detail toast. `pytest tests/ -q` green.

Watch out: `api()` throws on error, so the toast line only runs on success —
place it after, not before, `refresh()`.

### F2 — Clickable toggle switches (all `.switch` instances)

Goal: every toggle flips when clicking the pill itself, the label, or via
keyboard (Space).

Root cause (verified): `.switch .track` (`app/frontend/styles.css:218-225`) is
a full-size later sibling over the invisible `input`, with no `pointer-events`
handling — clicks hit the dead `span`. Affects `variantsSwitch`
(`index.html:52`), `hasHeader` (`index.html:78`), `forceRegen`
(`index.html:134`), and dynamic Bake inclusion toggles (`app.js:542-560`,
which have no `<label>` at all and are fully dead).

Files: `app/frontend/styles.css` (1-line fix); verify in `index.html`, `app.js`.

Steps:
1. Add to the `.switch .track` rule: `pointer-events: none;` (lets clicks fall
   through to the full-size `opacity:0` input; label `for=` associations are
   already correct and stay as-is).
2. Do NOT add JS click handlers — CSS `:checked + .track` needs none; values
   are polled on submit (`doNew()` reads `variantsSwitch.checked`, `doImport()`
   reads `hasHeader.checked`).
3. Keyboard check: Tab-focus each switch → Space flips → visual pill slides
   (`translateX(20px)`) and `forceRegen` still triggers `renderVoice`.

Verify: manual in browser/`--server-only`: click the pill, the knob, the label
text, and Space-key for all of: variants toggle, CSV-header toggle, force
toggle, one Bake inclusion toggle. `pytest tests/ -q` green (no backend change).

Watch out: do not use `display:none` on the input (kills keyboard access); do
not add `z-index` hacks — `pointer-events:none` is the whole fix.

### F3 — Rows table: keep both status pills, fix the styling (verdict on "obsolete")

Verdict: **you are wrong for multi-variant rows, right about the single-variant
look.** The two columns are different granularities sharing `statusChip()`:
Translations = N pills, one per variant (`app.js:242-250`); Status = 1 rollup
pill via `rowRollup()` (`app.js:254-256`, worst-case `error > stale >
generating > pending > ok`). With formal+informal ON they can diverge
(`ok + pending` vs rollup `pending`) — removing the per-variant pill loses
which variant needs work. With one variant they read duplicated.
Fix = keep both, remove the confusion: style the missing states and space the
pills.

Files: `app/frontend/styles.css`, `app/frontend/app.js` (spacing only).

Steps:
1. CSS: add `.chip-pending` (dashed paper, like `.chip-informal`) and
   `.chip-generating` (solid `var(--sun)` + existing `.pulse` dot or stripe;
   keep to one new animation-free style to stay minimal).
2. JS `statusChip()` (`app.js:156-164`): map `pending → chip-pending`,
   `generating → chip-generating` (keep `ok/stale/error` as-is).
3. Spacing (do not keep the `" " + text` hack in `app.js:246` as the only gap):
   give `.chip` `margin-right:6px; .chip:last-child{margin-right:0}` or a
   wrapping flex `gap:6px` on the variant `wrap` div — pick one, apply to both
   the Translations wraps (`app.js:243,248`) and inclusion list
   (`app.js:562-566`).
4. Do NOT delete either column.

Verify: `--server-only` with variants ON, 2 rows (one `ok`, one mixed
`ok+pending`): per-variant pills styled (no bare default `.chip`), rollup
correct, pills never touch text. `pytest tests/ -q` green.

### F4 — Minimal spacing style guide + apply it (status bars, CTAs, hints, pills)

Verdict: **true, the inconsistency is real.** Audit (`styles.css` 394 lines):
card padding uniformly `24px` (fine), but `.section-title{margin:28px 0 14px}`
as first-child inside a padded card stacks to ~52px; CTA→progress→text stacks
(`Build → .progress → p`, `Generate → table/audio`) have 0 inter-element gap
(`.btn`/`.progress` no margin, `p{margin:0}`); hints use two type styles
(`.hint` 13px grey vs bare `p#estimate/#voiceProgressText/#bakeProgressText`
16px ink, no top margin); `.chip` has no margin (gap = hardcoded `" "` in one
branch only); button rows use two gaps (modal `12px` vs row-actions `6px`).

Files: `app/frontend/styles.css`, `app/frontend/index.html`,
`app/frontend/app.js` (chip wraps), `AGENTS.md` (new section).

Steps:
1. Add 5 rules to `styles.css` (reuse existing scale only — `6px/12px/14px`):
   - `.card > .section-title:first-child{margin-top:0;margin-bottom:14px}` (kills
     52px stack; section-level titles outside cards keep `28px` top).
   - `.card > .btn,.card > .progress,.card > p{margin-top:12px}` with
     `:first-child` excluded (fixes CTA→feedback touching).
   - `p#estimate,p[id$="ProgressText"]{font-size:13px;color:var(--ink-60);margin-top:12px}`
     (extends `.hint` type to the three bare `<p>`s).
   - `.chip{margin-right:6px}.chip:last-child{margin-right:0}` (replaces `" "` hack).
   - New `.btn-row{display:flex;gap:12px;flex-wrap:wrap;margin-top:14px}` token;
     apply to download `<p>` (`index.html:176`), cancel buttons, future CTA
     groups. Keep `.row-actions:6px` as the dense-table exception.
2. Unify headless cards: Voice model card (`index.html:109-128`) and Bake build
   card (`167-172`) get either a heading or the same top rhythm — do not leave
   both patterns.
3. Append to `AGENTS.md` a `## WordTape frontend spacing rules (minimal)` section
   with exactly these 5 rules + the two tokens (card `24px`, content
   `32px 24px 96px`, max-width `1080px`). Keep under 30 lines — minimal-viable,
   not a design system.

Verify: open Words/Voice/Bake at 1280px, screenshot-compare: no 52px heading
gap, no touching CTA stacks, all bottom hints 13px grey with 12px top gap,
pills spaced without literal spaces. `pytest tests/ -q` green.

### F5 — Window tiling with Super+Left/Right

Root cause (verified against pywebview 6.2.1 `platforms/gtk.py`): window is
decorated + `resizable=True` (good), but `min_size=(1024,700)`
(`app/main.py:116` → `set_size_request(1024,700)`) exceeds a half-screen on
1080p/HiDPI-scaled displays (e.g. 1920/2 − dock < 1024) so Mutter refuses the
tile and it looks "not working".

Files: `app/main.py`, `app/frontend/styles.css` (+ `index.html` choice-grid from
F10 must also collapse — coordinate, don't duplicate).

Steps:
1. `app/main.py:116`: change `min_size=(1024,700)` → `min_size=(640,400)`.
   Keep `width=1280,height=800,resizable=True`, decorated (no `frameless`),
   no `fullscreen/maximized/on_top`.
2. CSS: add `@media (max-width:900px)`: `.content{padding:20px 16px 64px}`,
   `.row-table` horizontal scroll (`overflow-x:auto`, min-width preserved, do
   NOT reflow the 5-col grid into rows), choice-grid (F10) stacks to 1 col.
3. Do NOT set `minimum` anywhere else; do NOT force `x/y` position.

Verify: on GNOME/Mutter (Mint + Zorin): launch → Super+Left tiles to left
half, Super+Right to right half, drag-to-edge snaps, no snap-back; content
usable at 640px (scroll, no overlap). `pytest tests/ -q` green.

Watch out: lowering `min_size` without the media query leaves the rows grid
overflowing — both parts are required.

### F6 — "Your tape" CTA: open output folder + reveal file

Today (`index.html:173-178`, `app.js:572-581`): success card shows playback +
downloads + plain-text `outputPath` — no open/reveal action; no
`xdg-open|reveal` code in `app/`; only opener-dialogs (`pick_folder/pick_file`
in `app/main.py:61-109`, unused by frontend).

Files: `app/server.py` (new route), `app/main.py` or server-side opener (pick
one — server-side `xdg-open` works in browser-fallback too), `app/frontend/*`.

Steps:
1. Server: `POST /api/system/reveal {target: "folder"|"mp3"|"wav"}` —
   resolve against `config.export_dir(project)` only (reuse the `/export/`
   traversal guard pattern: `resolve()` + `is_relative_to`), then try in order:
   `["nautilus","--select",file]` → `["nemo","--select",file]` →
   `["xdg-open",folder]`; return `{opened:bool, selected:bool}` (selected=false
   on the `xdg-open` fallback). `subprocess.Popen` (do NOT block the job
   thread); on failure return 501 with detail, frontend toasts it.
2. Frontend success card: add `.btn-row` (F4 token) with `Open output folder`
   (primary-ghost) + `Show MP3` buttons; wire to the route; disable while no
   `track.exists`.
3. Microcopy: buttons exactly `Open output folder` / `Show MP3`; error toast
   reuses `Oof — the API said no. Check the key?`-style generic path (new
   string: `Couldn't open the folder. Path copied above.` — and select the
   `#outputPath` text on failure so the path is still reachable).

Verify: pytest new `test_server.py` cases (traversal `../../etc/passwd` → 404,
missing track → 404, mocked `Popen` success shape); manual on Mint (Nemo) and
Zorin (Nautilus): folder opens, MP3 pre-selected where supported.

Watch out: never pass user raw paths to the shell — allowlist to export dir;
never `check=True`/`capture_output` block the event loop (fire-and-forget
`Popen`).

### F7 — App Settings screen + Gemini API key (persisted, replaceable)

Today: key = env `GEMINI_API_KEY` → else baked `app/secrets.py` (`config.py:21-41`,
baked by `build.sh:27-35`); env overrides baked but there is NO UI
(`index.html` has no key input). SDK also reads `GOOGLE_API_KEY` but
`get_api_key()` ignores it — keep ignoring (document, don't expand scope).

Files: `app/config.py`, `app/server.py`, `app/frontend/*`, `app/main.py`
(boot order). New file: `app/settings_store.py`.

Steps:
1. `app/settings_store.py`: `load()/save(patch)` over
   `~/.local/share/WordTape/settings.json` (`XDG_DATA_HOME`-aware, `0o600`
   file perms, `mkdir -p`); schema `{gemini_api_key: str|null, export_root:
   str|null}` (export_root owned by F8 — include the key now, wire later).
   `clear` = set `null` (revert to env/baked). Never log the value.
2. `config.get_api_key()`: precedence user-setting → env → baked `secrets.py`;
   `apply_api_key_to_env()` unchanged in shape (called at boot in
   `main.py:25-29` AND re-called after a settings save so Translate/TTS pick up
   the new key without restart).
3. Server: `GET /api/settings` returns `{has_key:bool, key_hint:"…last4",
   export_root:str|null, export_default:str}` (NEVER the full key);
   `PATCH /api/settings {gemini_api_key?: string|null}` — empty string = clear;
   validate non-empty as plausible key (length ≥ 8, no whitespace-only);
   on save, re-resolve + return `has_key/key_hint`.
4. Frontend: topbar gear `⚙ Settings` button (NOT a 4th numbered stepper —
   settings is not part of the 01→03 sequence; see F10) opening a `Settings`
   screen/section with password input + `Save key` + `Remove key` + hint
   `Saved on this machine only. Takes effect immediately.` Toasts: `API key
   saved.` / `API key removed — using baked key.`
5. Tests: `settings_store` roundtrip (tmp `XDG_DATA_HOME`), precedence
   (setting beats env beats secrets), server masks key (no full key in any
   response body).

Verify: save key → restart app → still set (`has_key` true, hint stable);
remove → falls back to baked/env; Translate works after save without restart.
`pytest tests/ -q` green. Update README key section (baked → overridable).

Watch out: `import app.settings_store` lazily where possible (keep the
no-credentials-on-import rule); `settings.json` is gitignored — add it.

### F8 — Settings: user-defined output folder

Today: global root = `~/Music/WordTape/` else `<app>/output/`, override only
via `WORDTAPE_EXPORT_DIR` env (`config.py:78-89`); per-project subfolder
`<root>/<project>/` created by `assembler.build_track()` (`assembler.py:147-151`).
Not in `project.json` (correct — it is machine-specific, like the key).

Files: same Settings screen as F7 (`app/config.py`, `app/server.py`,
`app/frontend/*`).

Steps:
1. `config.export_dir()`: precedence `settings.export_root` → env
   `WORDTAPE_EXPORT_DIR` → Music → `<app>/output`. `export_root` = root only;
   project subfolder appended as today (no per-project override in this batch).
2. Server: extend `PATCH /api/settings` with `{export_root?: string|null}` —
   validate: must be absolute, must exist or be creatable (`mkdir -p` dry check
   at save, error toast otherwise); `null`/empty = reset to default. `GET`
   includes `export_root` + `export_default` + current `output_dir` per project
   (existing `_track_info` key, unchanged).
3. Frontend Settings screen: `Output folder` text input + `Browse…` (calls
   existing `window.pywebview.api.pick_folder()` with typed-path fallback for
   browser mode) + `Reset to default`; hint shows resolved default path.
   Toast: `Output folder updated.` Existing Bake `#outputPath` display + `/export/`
   serving keep working (they read `export_dir()`, no change needed).
4. Tests: `export_dir` precedence chain (mocked `music_dir` + tmp settings +
   env), PATCH validation (relative path → 400, unwritable → 400, null →
   default). Manual: set folder → Bake → MP3 lands in
   `<new-root>/<project>/final.mp3`, old files untouched (no migration).

Verify: set → rebuild → file in new root; reset → default restored; restart
persists. `pytest tests/ -q` green.

### F9 — Bake settings persistence (verify-only, no change expected)

Answer: **already the case — keep as is.** Bake knobs (`repeats`,
`repeat_gap_s`, `item_gap_s`, `voice`, `tts_model`) persist per-project in
`project.json` (`project.py:89-93` schema, `185-195` save, `258-262` load) via
`PATCH /api/project/settings` (`server.py:644-699`, validation `1-10`/`0-60`),
restored in `renderBake()` (`app.js:526-536`) + `renderVoice()` (`450-457`).
Session-only by design (NOT persisted): inclusion checkboxes (`unchecked:Set`,
`app.js:14,551-554`) and `forceRegen` — do not persist these in this batch.

Steps (verify only):
1. Run `pytest tests/test_project.py tests/test_server.py -q` — settings
   roundtrip green.
2. Manual: set repeats 5→3, gaps, voice → close app → reopen project → values
   intact; checkboxes reset (expected).
3. If and only if step 1 fails, fix `save/load` to include the missing key —
   do not invent a global settings file for bake (bake stays per-project; app
   globals live in F7/F8).

Verify: the two checks above pass; no code diff required. If a diff was needed,
state which key was missing.

### F10 — Project vs Open as side-by-side choice cards

Agreed — **yes, change it.** They are alternative entries to the same thing
(new vs existing), not steps 1→2, so the current vertical stack misleads the
user into reading them as a top-to-bottom flow. Common pattern: parallel
choice cards in one row with equal weight (design-lead: numbered `01/02/03`
markers encode sequence and must NOT be used here; a plain `or` divider does).

Files: `app/frontend/index.html`, `app/frontend/styles.css`.

Steps:
1. Wrap the two cards (`index.html:23-57` Project + `58-69` Open) in
   `<div class="choice-grid">`; keep each card's contents, ids
   (`newName/newSource/newTarget/swapLangs/variantsSwitch/newProjectBtn`,
   `openPath/openBtn/recentList`), `--i` animation indices, and validation
   untouched.
2. CSS: `.choice-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;
   align-items:start}` + `@media (max-width:900px){.choice-grid{grid-template-columns:1fr}}`
   (stacks on narrow tiled windows — pairs with F5). Both cards keep `.card`
   padding/border; headings stay `Project` / `Open project`; add a small
   `or` divider label between them on desktop only (CSS `::after` or a
   `.choice-or` span — pick one, keep it 12px uppercase grey, aria-hidden).
3. Do NOT renumber the `01 Words / 02 Voice / 03 Bake` stepper; do NOT move
   Import/Rows/Add cards.

Verify: at 1280px the two cards sit equal-height side by side; at 700px tiled
width they stack without overlap; keyboard/validation/toast behavior unchanged
(F1 still fires). `pytest tests/ -q` green (frontend-only change).

### Batch definition of done

- Each F-spec above has its Verify actually run; `pytest tests/ -q` green.
- `--server-only` click-through of Words → Voice → Bake still works; new
  Settings screen reachable from the topbar on both webview and browser fallback.
- README updated for Settings (key override + output folder) and tiling
  `min_size`; AGENTS.md carries the 5-rule spacing guide (F4).
- One commit per F-spec (or one per merged PR), no secrets in `git show`.

---

---

## Spec: WordTape cost estimates — per-call toasts + monthly ledger (done 2026-10-11)

Status: **complete (2026-10-11)**. F11 + F12 implemented and verified (est.
suffixes only when usageMetadata reported; local ledger + Settings costs card;
183 mocked tests green). Verdict: **literal request skipped, estimate
variant feasible and specced below (F11–F12).**

### Verdict (report-back: possible as estimates, not as billed cost)

- The Gemini API (`generate_content` via `google-genai>=2.25.0`) returns **no
  dollar cost field**. It returns `response.usage_metadata` token counts only
  (`prompt_token_count`, `candidates_token_count`, `total_token_count`, plus
  per-modality `prompt_tokens_details` / `candidates_tokens_details`). No code
  in the repo reads it today (grep for `usage_metadata|cost|price` = 0 hits in
  `*.py`; `backends/gemini.py:74-84` reads only `response.parts`; 
  `app/translate.py:101-102` reads only `response.text`).
- There is **no billing API readable with just `GEMINI_API_KEY`**. Cloud Billing
  (`cloudbilling.googleapis.com`) needs GCP OAuth + IAM, not the AI Studio key.
  Spend truth lives in AI Studio Billing / Cloud Console only.
- Feasible path: **estimate locally** = `usage_metadata × pricing table`, show
  `~$X est.` in toasts, accumulate into a local monthly ledger. Every cost
  shown must be labeled `est.` — never "final"/"charged".
- Pricing table (Standard tier, `https://ai.google.dev/gemini-api/docs/pricing`;
  TTS GA 2026-09-22, introductory through Dec 31 2026, **doubles Jan 1 2027**):
  - `gemini-3.8-flash-lite-tts`: text-in $0.50/1M, audio-out $6.00/1M
    (→ $1.00 / $12.00 in 2027).
  - `gemini-3.8-flash-tts`: text-in $0.50/1M, audio-out $9.00/1M
    (→ $1.00 / $18.00 in 2027).
  - `gemini-3.5-flash-lite` (translation): text-in $0.30/1M, text-out $2.50/1M,
    cached-in $0.03/1M (ignore cached unless `cached_content_token_count` > 0).
  - TTS audio tokens ≈ 25 tok/s; modality comes from
    `candidates_tokens_details[{modality:AUDIO}]`. If details are absent, treat
    all candidates tokens as AUDIO for TTS models, as TEXT for the translation
    model. `voices.list` costs nothing — exclude it.
- Retry/parse-retry calls each cost money — count every actual
  `generate_content` invocation (including translation `_RETRY_SUFFIX` retries
  and per-item 2s/4s/8s retries), not just logical batches.

### F11 — Per-call estimated cost in toasts (translate, test-voice, TTS list)

Goal: after each billable action the existing toast gains an estimate suffix,
e.g. `Translated 10 rows (~$0.004 est.)`, `Baked 30 clips (~$0.021 est.)`,
sample playback shows `Sample ready (~$0.0004 est.)`.

Files: new `app/costs.py`; touch `backends/gemini.py`, `backends/base.py`,
`app/translate.py`, `app/tts.py`, `app/server.py` (job messages), 
`app/frontend/app.js` (toast strings only).

Steps:
1. `app/costs.py` (new, pure, no credentials): `PRICING` dict keyed by exact
   model id with `{input_per_1m, audio_per_1m, text_out_per_1m,
   effective_from:"2026-09-22", doubles_on:"2027-01-01"}` + `_rate_for(model,
   date)` handling the 2027 doubling + `estimate_translate(usage)` (prompt ×
   in + candidates × text-out + cached × cached-in) and `estimate_tts(usage,
   model)` (prompt-TEXT × in + candidates-AUDIO × audio-out) + `fmt_est(usd)`
   (`~$0.004`, 4 decimals under $0.01 else 2). All readers use `getattr`
   defensively — `usage=None` → return `None` (caller omits the suffix, never
   `$0.00`).
2. `backends/base.py`: add optional fields to `SynthesisResult`
   (`prompt_tokens:int|None=None, candidates_tokens:int|None=None,
   estimated_cost_usd:float|None=None`) — keep positional order so existing
   constructions don't break.
3. `backends/gemini.py:_synthesize_one`: return `(wav_bytes, usage)`; on the
   success path compute `costs.estimate_tts(getattr(response,
   "usage_metadata", None), self.model)`; `synthesize_many` attaches per-item
   `estimated_cost_usd` (failed items: `None`). Retries: each attempt that got
   a response counts — simplest correct rule: cost of the successful attempt
   only, plus a `*_all_attempts_usd` sum if trivial; document whichever is
   chosen in the docstring.
4. `app/translate.py:translate_rows`: add kwarg `collect_costs:list|None=None`
   (default keeps the `dict` return shape so existing tests don't break);
   after each `_call_with_retries` (first try AND `_RETRY_SUFFIX` retry),
   append `estimate_translate(getattr(resp,"usage_metadata",None))` when not
   `None`. `_call_with_retries` must return the raw response (it already does)
   — do not change its retry/backoff behavior.
5. `app/tts.py:generate_audio` / `test_voice`: sum per-result
   `estimated_cost_usd` (skip `None`); return `(results, total_usd)` — or keep
   return shape and add optional `collect_cost:dict|None` out-param if changing
   the tuple breaks callers; pick one and update `app/server.py` call sites
   (`server.py:201,245,562`) to include `~$X est.` in the job `message` and in
   the JSON the frontend toasts. `test_voice` (single clip, `tts.py:98-113`)
   returns bytes today — add cost via response header (`X-Est-Cost-USD`) or a
   `{audio_b64, estimated_cost_usd}` envelope on a NEW route version; do NOT
   break the existing `/api/voice/test` bytes contract without bumping the
   frontend together.
6. Frontend: toast strings only — append `(~$X est.)` when the server reports a
   cost; when cost is absent (old cache, mocks, `usage=None`) keep today's
   exact strings. Never show the word "final" or "charged".

Verify: pytest with `SimpleNamespace(usage_metadata=SimpleNamespace(
prompt_token_count=29, candidates_token_count=92, prompt_tokens_details=[...],
candidates_tokens_details=[{modality:AUDIO...}]))` → TTS-lite ≈
29/1M×$0.50 + 92/1M×$6.00; translate batch ≈ prompt×$0.30 + candidates×$2.50;
`usage=None` → suffix omitted. All existing tests green (return-shape
backward compat). Manual `--server-only`: translate 1 row + test voice show
`est.` suffix.

Watch out: never call `.text` on TTS responses or `.parts` assumptions on
translate; never block synthesis on costing (wrap estimate in try/except →
`None`); keep `backends/` credential-free.

### F12 — Settings: current-month estimate + past-months table (local ledger)

Goal: Settings screen (F7/F8) gains a `Costs (estimates)` card: current
calendar-month total + a past-months table. No billing integration — local
ledger only, labeled as such.

Files: new `app/cost_ledger.py`; touch `app/server.py` (record + `GET
/api/costs`), Settings frontend, `.gitignore`.

Steps:
1. `app/cost_ledger.py`: JSON file `~/.local/share/WordTape/costs.json`
   (`XDG_DATA_HOME`-aware, same dir family as F7 `settings.json`; gitignored).
   Schema `{"months": {"2026-10": {"translate_usd":…, "tts_usd":…,
   "calls":…, "updated_at":…}}, "pricing_version":"2026-09-22+intro"}`.
   `record(kind:"translate"|"tts", usd:float)` rounds to 6 decimals, creates
   the current `%Y-%m` bucket, writes atomically (`tmp` + `os.replace`),
   never raises into the synthesis path (caller wraps in try/except).
2. Server: call `record()` on every successful billable completion (translate
   job, `generate_audio` job, `test_voice` single — including $0-est skips as
   calls with 0); `GET /api/costs` → `{current_month:"2026-10",
   current:{translate_usd,tts_usd,total_usd,calls}, history:[{month,
   translate_usd,tts_usd,total_usd,calls}…] desc, pricing_version,
   note:"Estimates from usageMetadata × Standard-tier table. Authoritative
   spend: AI Studio Billing."}`. Month key = server local `%Y-%m`; no
   month-end charge logic (the API is pay-as-you-go/prepay — the table is a
   calendar-month accumulator, not an invoice).
3. Frontend Settings card: `Costs (estimates)` — current month line
   (`October 2026: ~$0.42 est. (translate ~$0.05 + voice ~$0.37, N calls)`),
   table `Month | Translate | Voice | Total | Calls` (past months desc, current
   month first row highlighted), footnote `Estimates only — check AI Studio
   Billing for actual charges. Introductory TTS pricing ends Dec 31, 2026;
   rates double Jan 1, 2027.` Empty state: `No API calls recorded yet.`
4. Tests: ledger roundtrip (tmp `XDG_DATA_HOME`), month-bucket rollover (fake
   `%Y-%m`), rounding, atomic write; server test that a mocked translate+tts
   run increments `GET /api/costs`; frontend manual: costs survive restart,
   table grows across fake months.

Verify: `pytest tests/ -q` green incl. new `test_costs.py` + `test_cost_ledger.py`;
manual: real translate+generate → Settings total increases by ≈ toast sums;
restart persists; empty ledger shows empty state.

Watch out: one ledger write per logical job completion (not per poll); concurrent
jobs reuse the F-batch single-job guard — still lock the JSON write; never store
the API key in `costs.json`.

### Batch definition of done

- Toasts show `(~$X est.)` only when usage was reported; otherwise today's
  strings byte-identical. No UI ever says "final cost" or "charged".
- Settings costs card + history table read from local ledger; empty state works.
- `pytest tests/ -q` green; README gains a `Costs (estimates)` paragraph
  (usageMetadata × table, intro-pricing expiry, AI Studio Billing as truth).

## Spec: WordTape fixes batch 3 — drag-n-drop import, target-language synonyms (done 2026-10-13)

Status: **complete (2026-10-13)**. Both bugs fixed and verified: 188 mocked tests green (+5 new: path-import txt/csv/errors, source-echo discard, stale-register removal); browser click-through (project create, file drop → "Imported 3 rows.", text/uri-list fallback via path import, no-project microcopy, per-row ⇄ action); path-mode import exercised live via curl. The packaged-app native drop (pywebview DOM drop handler in `app/main.py`) needs one manual check on the Zorin machine — the GTK bridge cannot be driven from here.

### B1 — Drag-n-drop import does nothing (webview)

Goal: dropping a `.txt`/`.csv` file on the app imports it, in the packaged
(GTK/WebKitGTK) app **and** in browser fallback.

Root cause (verified in pywebview 6.2.1 sources): the packaged app runs the
GTK backend. pywebview only exposes dropped-file paths when the drop is
observed through its DOM API — `element.on('drop', …)` bumps
`_dnd_state['num_listeners']`, which arms the GTK `drag-data-received` hook
that collects the `file://` URIs and injects `pywebviewFullPath` into each
file of the DOM event. Our plain JS `addEventListener` on `#dropzone` never
gets a path, and WebKitGTK's `dataTransfer.files` is empty there, so
`files.length > 0` is false and the handler silently returns. Secondary:
`FileReader`/handler errors are unhandled promise rejections (no toast);
drops only register over the small dropzone; click-to-pick ignores the
already-implemented `Api.pick_file` bridge.

Files: `app/server.py`, `app/main.py`, `app/frontend/app.js`,
`app/frontend/index.html`; tests in `tests/test_server.py`.

Steps:
1. Server: extend `POST /api/project/import` to accept `path` (absolute
   filesystem path) as an alternative to `content` — mutually exclusive
   (`400` when both or neither given). Path mode: reject non-str, non-`.txt`/
   `.csv` extensions (400 with detail), missing/non-file (404), > 5 MiB (400);
   read bytes, decode `utf-8-sig` (same as browser uploads); then reuse the
   existing parse → `proj.rows.clear()` + `insert_row` → `save_project`
   replace semantics. Response shape unchanged (`{"imported": N}`).
2. `app/main.py`: after the window is shown, register pywebview DOM handlers —
   `drop` on `#dropzone` **and** on the document (whole-window drops), plus
   `dragover` with `prevent_default=True` on the same elements so WebKitGTK
   allows the drop. The drop callback reads
   `event['dataTransfer']['files'][*]['pywebviewFullPath']` (fallback: the
   `name`/`file://` URI from `text/plain` payload) and forwards the first path
   to the page: `window.evaluate_js('window.__wordtapeNativeDrop(<json>)')`.
3. `app/frontend/app.js`:
   - `window.__wordtapeNativeDrop(path)` → `needProject()` gate, then POST
     `/api/project/import` `{path, has_header}` → `refresh()` → existing
     `Imported N rows.` toast.
   - Keep the HTML5 handlers for browser mode; add a `text/uri-list` (then
     `text/plain`) fallback that extracts a `file://` path and calls the same
     import-by-path flow; dedupe so a drop handled natively within ~1 s is
     not double-imported by the JS handler.
   - Wrap the whole drop/import flow in try/catch with a toast on failure (no
     more silent rejections).
   - Click-to-pick: prefer `window.pywebview.api.pick_file(['txt','csv'])`
     (returns a path → import-by-path); fall back to `<input type=file>`.
4. `app/frontend/index.html` / microcopy: `#dropText` when no project is open
   reads `Create or open a project first — then drop a .txt or .csv here.`
   (set from `refresh()`/`renderRows()`); keep the "project required" toast.

Verify: `pytest tests/ -q` green incl. new path-import tests; manual: in
`--server-only` browser mode, drop a .txt → rows appear, bad path → toast;
in the packaged app, drop a .txt anywhere on the window → rows appear;
click the dropzone in the packaged app → native picker opens.

Watch out: import still requires an open project (by design); path imports
bypass the browser sandbox, so the extension/size/exists checks are the
security boundary — the server is localhost-only, never expose it.

### B2 — Formal/informal synonyms come back in the source language

Goal: with `variants_enabled`, `formal`/`informal` variants are alternative
renderings of the **translation, in the target language** — never register
variants of the source term.

Root cause: `_build_prompt` says `formal/informal = alternatives with exactly
the same meaning` without naming the term or the language, and asks for an
unused `"source"` echo — the model reasonably returns source-language
variants. Nothing rejects them downstream.

Files: `app/translate.py`, `app/server.py`; tests in `tests/test_translate.py`,
`tests/test_server.py`.

Steps:
1. `_build_prompt` (variants branch): response keys become `"translation"`,
   `"translation_formal"`, `"translation_informal"`; drop `"source"` from the
   schema (positional mapping stands — documented decision). Wording states
   all three fields are translations **in `{target_lang}`**, never in
   `{source_lang}`, that formal/informal are alternative renderings of the
   translation (same meaning, different register), `null` when the language
   makes no such distinction, and `Never translate names.` stays.
2. `translate_rows`: read the new keys (`entry.get("translation_formal")` /
   `("translation_informal")`); still tolerates extra keys. New guard: a
   register value equal to `row.source` after strip+casefold is discarded
   (→ `None`) — a source-language echo is never stored. Return shape stays
   `{"translation", "formal", "informal"}`.
3. `_translate_run` apply semantics: when `variants_enabled` and a register
   comes back null/empty, **remove** any existing formal/informal variant of
   that row (plus its cached wav via `audio_path`) instead of keeping stale
   text — a re-run therefore repairs rows. Upsert-and-overwrite for non-empty
   values stays as today.
4. Frontend: per-row "⇄" ghost action ("Re-translate this row") →
   `POST /api/translate {row_ids:[row.id]}` (endpoint already supports it) →
   existing `startPoll(…, "voice", …)` + `Translated N rows.` toast.

Verify: `pytest tests/ -q` green (prompt assertions updated to the new keys;
new tests: source-echo discarded, null register removes stale variant);
manual: toggle on, translate → formal/informal chips show target-language
text; a row with old source-language synonyms re-translated → replaced.

Watch out: keys `formal`/`informal` are internal from here on (project.json,
API payloads, UI chips keep style names `main`/`formal`/`informal`) — only the
Gemini response schema changes.

### Batch definition of done

- Dropping a .txt works in both the packaged app and browser mode; failures
  toast instead of vanishing.
- Synonyms are target-language; source-language echoes are impossible to
  store; re-run clears/fixes previously wrong rows (per-row action).
- `pytest tests/ -q` green; README import/translation notes updated if needed.
