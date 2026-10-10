# TODO

## Spec: Gemini 3.8 TTS backend migration

Status: **complete (2026-10-10)**. All 12 tasks finished and verified
(31 mocked tests green; live smoke test: WAV probe `24000 1 2`, single RIFF header).
Finished items moved to [TODO-DONE.md](TODO-DONE.md).

### Follow-ups (out of scope, still open)

- **Batch API** (half price): deferred. No official TTS-in-batch worked example exists and the batch JSONL parser reportedly requires snake_case fields; not worth the risk at this scale. Revisit with a spike if cost ever matters. The `batch_jobs.json` resume design is unnecessary while sync-only.
- **Interface phase:** own spec in TODO.md once this backend is stable (deployment options are sketched in `IDEA.md`). The boundary contract for it is: import `backends/`, call `synthesize_many(items, progress=..., cancel=...)`, write the yielded WAV bytes.
- **Per-line style / multi-speaker:** interface-era features.

---

## Spec: WordTape — executable UI for vocabulary drill audio

Status: **ready for execution** (branch `executable-ui`). Purpose: a desktop executable for
two users (personal, no auth, API key baked in) that turns a word list into a repeating
"listen and repeat" drill track.

### Context

The backend migration (see TODO-DONE.md) left a reusable `backends/` package
(`synthesize_many(items, progress, cancel)`, `list_voices`). This spec builds the desktop app
on top of it. Decisions gathered from the user:

- **App shell:** native window via **pywebview**, with automatic fallback to the system
  browser if the webview cannot start (see Trap 1).
- **Post-processing:** row editor + local rebuild (approved shape).
- **Final file:** always MP3 (bundled ffmpeg) + WAV byproduct.
- **Languages:** source+target pickers, defaults **German → Indonesian** (one constant to change).
- **Track shape:** every translation played **5×** (editable), **1.2 s** break between plays
  (editable), **1.8 s** gap between items (editable). Source language is NOT in the track.
  NOTE: the user's old "estimated break" source code was searched for exhaustively (all of
  ~/Code, git history, session archives, trash) and is **not on this machine** — these values
  are the agreed replacement and are editable in the UI.
- **AI models (verified live against the API on 2026-10-10):**
  - Translation (text): `gemini-3.5-flash-lite` — the newest Flash-Lite **text** model that
    exists (`gemini-3.6-flash-lite` and `gemini-3.8-flash-lite` return 404; "3.8 Flash-Lite"
    exists only as a TTS model). Good intelligence, low cost. Constant in `app/config.py`.
  - TTS: `gemini-3.8-flash-lite-tts` (default) / `gemini-3.8-flash-tts` (quality option).
- **API key:** baked into the executable at build time from `.env` (explicitly requested;
  tool is for the user + wife only). See security note in Tasks.
- **Build targets:** one Linux binary, built on this machine (Linux Mint 22.3, glibc 2.39),
  must run on Linux Mint **and** Zorin. See Trap 2 for the glibc fallback.

Working name **"WordTape"** (changeable: one constant `APP_NAME` in `app/config.py`).

### Execution rules for the implementing agent

1. Work the phases below in order (A → G). Do not renumber or delete task items — check them
   off in place. When everything is done and verified, move finished items to `TODO-DONE.md`.
2. Every task has a `Verify` step. Run it before checking the box.
3. "Watch out" notes are pre-approved solutions. Follow them literally — they encode traps
   found by prior research.
4. Frontend is **plain HTML/CSS/JS with no build step**. No React, no bundler, no npm. This
   is deliberate (PyInstaller + a simple executor).
5. Reuse `backends/` for TTS — do not write new TTS request code. Translation code is new
   (`app/translate.py`) and uses `google-genai` directly.
6. Never commit `app/secrets.py`, `.env`, `dist/`, `build/`, `projects/`.

### Settled decisions

| Topic | Decision |
|---|---|
| Shell | pywebview native window (1280×800, min 1024×700), browser fallback |
| Backend server | FastAPI + uvicorn on 127.0.0.1, free port, uvicorn in daemon thread |
| Frontend | vanilla HTML/CSS/JS served by FastAPI, no build step |
| Persistence | one `project.json` per project folder + `audio/` cache + `output/` (JSON, not SQLite) |
| Import | `.txt` (one term per line → auto-translate) or `.csv` (2 cols: source, translation) |
| Variants | toggle: also generate formal + informal translations with the same meaning |
| Translation | `gemini-3.5-flash-lite`, batched 25 rows/call, JSON output |
| TTS | `backends.GeminiBackend`, `gemini-3.8-flash-lite-tts` default |
| Voice testing | per-voice "Test" plays a sample before batch generation |
| Track assembly | pure-Python WAV concat (stdlib `wave`), silence = zero frames |
| MP3 | bundled ffmpeg (via `imageio-ffmpeg` binary copied at build), libmp3lame |
| Post-processing | rows screen: edit text, regenerate row, insert at row N / end, delete, move, rebuild |
| Tests | pytest, mocked clients (stdlib `unittest.mock`), reuse `tests/helpers.py` FakeBackend |

### Architecture

```
app/
  main.py          # entry point: freeze_support, uvicorn thread, webview window, browser fallback
  config.py        # APP_NAME, model IDs, defaults, resource_path(), key resolution
  secrets.py       # GITIGNORED, generated by build.sh: API_KEY = "..."
  server.py        # FastAPI app + routes (below)
  project.py       # project.json load/save (atomic), Row/Variant dataclasses, row ops
  translate.py     # gemini-3.5-flash-lite: translate + formal/informal variants (batched)
  tts.py           # wraps backends/ for per-row audio cache + progress/cancel jobs
  assembler.py     # pure-Python WAV concat (5x + gaps) → final.wav; ffmpeg → final.mp3
  ffmpeg_bin/      # GITIGNORED; ffmpeg binary copied here at build (dev: imageio_ffmpeg)
  frontend/
    index.html     # three screens + toasts/modal, one <div data-screen> per screen
    styles.css     # design tokens + components (spec below)
    app.js         # vanilla JS: state, fetch API, render, polling
    fonts/         # vendored woff2 (committed): Fraunces + Karla
tests/
  test_project.py test_translate.py test_tts.py test_assembler.py test_server.py
build.sh           # fonts check, ffmpeg copy, secrets.py, pyinstaller
build-docker.sh    # fallback: same build inside ubuntu:22.04 (glibc 2.35) container
```

Data model (`project.json`, versioned):

```json
{
  "version": 1,
  "source_lang": "de", "target_lang": "id",
  "variants_enabled": false,
  "tts_model": "gemini-3.8-flash-lite-tts", "voice": "Kore",
  "repeats": 5, "repeat_gap_s": 1.2, "item_gap_s": 1.8,
  "rows": [
    {
      "id": "a1b2c3", "position": 1,
      "source": "Guten Morgen",
      "variants": [
        {"id": "v1", "style": "main", "text": "Selamat pagi",
         "audio": "audio/a1b2c3_v1.wav", "status": "ok"},
        {"id": "v2", "style": "formal", "text": "Selamat pagi, Bapak/Ibu",
         "audio": "audio/a1b2c3_v2.wav", "status": "stale"}
      ]
    }
  ]
}
```

- `status`: `pending` | `generating` | `ok` | `stale` (text edited since generation) | `error`.
- Row `id`/variant `id` are random 6-char hex — **never** derived from display position, so
  insert/delete/reorder cannot break audio cache file names.
- Atomic save: write `project.json.tmp` then `os.replace`.

### API surface (FastAPI, all JSON)

| Method & path | Purpose |
|---|---|
| `GET /api/state` | full project state (for UI render) |
| `POST /api/project/new` `{name, source_lang, target_lang, variants_enabled}` | create project folder |
| `POST /api/project/open` `{path}` | open existing project |
| `POST /api/project/import` `{filename, content, kind, has_header}` | parse txt/csv → rows (replaces rows) |
| `POST /api/translate` `{row_ids?}` | translate pending rows (runs as job) |
| `PATCH /api/rows/{id}` `{source?, variants?}` | edit text → variant(s) become `stale` |
| `POST /api/rows` `{after_row_id?, position?, source, translation?}` | insert row at end / after row N |
| `DELETE /api/rows/{id}` | delete row (also deletes its audio files) |
| `POST /api/rows/{id}/move` `{direction: up\|down}` | reorder |
| `GET /api/voices?model=&language=` | wrap `backends.list_voices` |
| `POST /api/voice/test` `{voice, model, text}` | one-off clip (not saved) → returns WAV bytes |
| `POST /api/tts/generate` `{variant_ids?, force?}` | generate stale/missing audio (job) |
| `POST /api/track/build` | assemble final.wav + final.mp3 (job) |
| `GET /api/jobs/{id}` | `{done, total, message, error, cancelled}` |
| `POST /api/jobs/{id}/cancel` | set cancel flag (backends already support cancel callback) |
| `GET /media/{project}/{path}` | serve cached audio / output files to `<audio>` tags |
| `GET /` + `/static/*` | serve frontend |

Job pattern (keep it dead simple): a module-level `jobs: dict[str, Job]`, `Job` is a
dataclass with `done/total/message/error/cancelled` + `threading.Lock`. Work runs in a
`threading.Thread`. UI polls `/api/jobs/{id}` every 500 ms. One job at a time (409 on new
job while one runs).

### Design brief (implement literally)

**Direction:** "sleek & sassy editorial language-lab" — warm cream paper, deep ink, one hot
accent. Confident big type, sticker-like chips, subtle grain, a wink of neo-brutalism on
buttons (hard offset shadow). Light theme only. Desktop window only (no responsive/mobile).

**Fonts** (vendor woff2 into `app/frontend/fonts/`, `@font-face`, `font-display: swap`;
download once at implementation time and commit — licenses are OFL):
- Display: **Fraunces** (soft wonky serif — the "sass"), weights 400/600, incl. italic.
- UI/body: **Karla** (grotesk with quirks), weights 400/500/700.
- Durations/timecodes: `ui-monospace` stack (system).
- Fallbacks so the app works even if fonts fail: `"Fraunces", Georgia, serif` /
  `"Karla", system-ui, sans-serif`.

**Tokens** (`:root` in styles.css — use exactly):

```css
--paper:#F7F1E7; --paper-2:#FFFDF8; --ink:#16120F; --ink-60:#5C5348;
--tangerine:#FF4D2D; --teal:#0F4C4A; --sun:#FFC94A; --line:#16120F1F;
--r-lg:18px; --r-md:12px; --r-sm:8px;
--shadow-pop:4px 4px 0 var(--ink); --font-d:"Fraunces",Georgia,serif;
--font-u:"Karla",system-ui,sans-serif;
```

**Shell:** sticky top bar (`WordTape` in Fraunces italic + project name + dirty-dot).
Horizontal stepper with oversized numerals: `01 Words` `02 Voice` `03 Bake` (current step:
tangerine underline + filled numeral; completed: small ✓). Content column `max-width:1080px`,
centered, `padding: 32px 24px 96px`. Section headings Fraunces 28px. Cards: `--paper-2`,
`1px solid var(--line)`, `--r-lg`, padding 24px.

**Screens:**
1. **01 Words** — hero line (Fraunces italic, 34px): *"Turn words into a drill tape."*
   Language row: two selects (Source → Target) + swap button (⇄). Drop zone (dashed 2px
   `--ink-60`, `--r-lg`, 180px) for `.txt`/`.csv` + hidden file input + "CSV has header row"
   checkbox + variants **Switch** labeled *"Also make formal + informal versions"*.
   After import: **Rows table** (`#`, Source, Translations (chips: `main`/`formal`/`informal`),
   Status chip, actions). Row actions as small ghost buttons: `Edit` (inline text inputs),
   `↻ Regenerate`, `↑`, `↓`, `+ Below`, `✕`. Bottom: *"Add a row at the end"* inline form and
   *"Add at row #N"* number input. Primary button *"Translate missing rows"* (tangerine,
   `--shadow-pop`, hover: translate(-1px,-1px) shadow 5px).
2. **02 Voice** — model select (two options with short descriptions), voice select (loaded
   from `/api/voices`, grouped optgroup by language if provided; note under it: *"Voices are
   multi-language — language tags on some voices are incomplete"*), sample text input
   (defaults to first row's translation), **"Test voice"** button → inline `<audio controls>`.
   Then *"Generate audio for all rows"* (or *"Regenerate N stale"*) with a chunky ProgressBar
   (tangerine fill, `--r-sm`, 14px) + Cancel button while a job runs.
3. **03 Bake** — settings card: three number steppers (*Plays per translation* 5,
   *Break between plays (s)* 1.2, *Gap between items (s)* 1.8) + live **duration estimate**.
   Inclusion checkboxes per variant (default all on) in a compact list.
   *"Build the drill tape"* button → progress → success card with `<audio controls>` for
   `final.mp3`, download buttons **Download MP3** / Download WAV, and
   *"Open output folder"* (shows the path in a mono chip — no OS file manager call needed).

**Components (CSS classes to implement):** `.btn` (base), `.btn-primary` (tangerine,
shadow-pop), `.btn-ghost`, `.btn-danger`, `.chip` + `.chip-main/.chip-formal/.chip-informal/
.chip-ok/.chip-stale/.chip-error`, `.switch` (toggle, 44×24, tangerine when on), `.dropzone`,
`.row-table` (grid: 48px 1.2fr 2fr 120px 200px), `.progress` (`.progress > i` inner fill),
`.stepper-num`, `.toast` (fixed bottom-center, ink bg, paper text, auto-hide 3.5 s),
`.modal-backdrop` + `.modal` (confirm delete only), `.field` (label + input/select).

**Motion (CSS only):** screen change → children get `animation: rise .28s ease both` with
`animation-delay: calc(var(--i) * 40ms)` (set `--i` inline per block); `@keyframes rise`
from `opacity:0; translateY(8px)`. Button `:active { transform: translate(2px,2px) }` and
shadow shrink. `.progress > i` uses a slowly moving stripe background while running.
`.pulse` (tangerine dot pulse) on the stepper's current numeral. No JS animation libs.

**Microcopy (use exactly):** empty import: *"No words yet — drop a .txt or .csv here and
let's cook."*; test voice: *"Make some noise"*; generate: *"Bake {n} clips"*; build:
*"Build the drill tape"*; toasts: *"Imported {n} rows."*, *"Translated {n} rows."*,
*"Row {n} is stale — regenerate it."*, *"Tape is ready. {duration} of pure repetition."*;
errors: *"Oof — the API said no. Check the key?"*; delete confirm: *"Delete this row and its
audio?"* / buttons *Keep it* / *Delete*. Keep humor short and never in error details.

**Accessibility floor:** focus-visible outline `3px solid var(--sun)` offset 2px, all
controls keyboard-reachable, `<label>` for every input, `aria-live="polite"` on toasts,
contrast ink-on-paper ≥ 12:1.

### Tasks

#### Phase A — Scaffold & data

- [ ] A1. Create `app/` package skeleton (empty modules as in Architecture) + `app/config.py`
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

- [ ] A2. `app/project.py`: dataclasses `Row`, `Variant`, `Project` with `load/save`
  (atomic `os.replace`), `new_project(folder, ...)`, and row ops:
  `insert_row(position, source, translation)`, `delete_row(id)`, `move_row(id, up|down)`,
  `update_variant_text(id, text)` (sets `status="stale"`), `mark_generating/ok/error`.
  Audio cache path: `audio/{row_id}_{variant_id}.wav`. `ensure_unique_ids()` on load.
  **Watch out.** Insert "at row N" = insert **before** current row N (1-based display);
  renumber `position` after every op; never renumber file names (ids are stable).
  **Verify.** `pytest tests/test_project.py` — roundtrip save/load, insert-before-N, delete,
  move boundaries (first/last), text-edit marks stale.

- [ ] A3. Import parsing in `app/project.py` (or `app/importer.py` if it grows):
  `parse_txt(content) -> list[str]` (strip, skip empty); `parse_csv(content, has_header)`
  → `list[tuple[str, str]]`. Encoding `utf-8-sig` (BOM!), delimiter via `csv.Sniffer`
  with fallback: if parsing yields 1 column, retry with `;` then `\t` (European Excel!).
  **Watch out.** Danish/German Excel exports semicolon-separated CSVs with a UTF-8 BOM —
  both handled here; `csv.Sniffer` alone is unreliable on short files, hence manual retries.
  **Verify.** `pytest tests/test_project.py -k import` — includes a semicolon+BOM fixture.

#### Phase B — Services

- [ ] B1. `app/translate.py`: `translate_rows(rows, source_lang, target_lang, with_variants)`
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

- [ ] B2. `app/tts.py`: `generate_audio(project, variant_ids=None, force=False, progress,
  cancel)` — wraps `backends.gemini.GeminiBackend` (`synthesize_many` already yields
  progress/cancel). Writes WAVs to the cache path; sets per-variant status. `test_voice(
  voice, model, text) -> bytes` (one-off). `list_voices(model, language)` delegates to
  `backends`. Language passed via `SynthesisRequest.language` for lookup only (TTS
  auto-detects the text).
  **Watch out.** Skip `status=="ok"` unless `force` or `status=="stale"`; build the request
  list with the **stable variant ids** in `index` field so results map back correctly.
  **Verify.** `pytest tests/test_tts.py` with a FakeBackend: stale-only regeneration, force,
  cache file naming, progress callback counts.

- [ ] B3. `app/assembler.py`: `build_track(project, included_variant_ids) -> (wav_path,
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

- [ ] B4. Job manager `app/jobs.py`: `start(kind, fn) -> job_id`, `get(job_id)`,
  `cancel(job_id)`, `Job` dataclass as described in the API surface. One active job (409).
  **Verify.** `pytest tests/test_server.py::test_jobs` — progress visible, cancel stops.

#### Phase C — Server

- [ ] C1. `app/server.py`: FastAPI app implementing **every route in the API surface table**
  exactly (paths, verbs, payload keys). `StaticFiles` for `/static`, `FileResponse` for
  `/media/*` with a path-traversal guard (resolve + must stay under the project folder).
  Frontend served at `/` (index.html). CORS not needed (same origin).
  **Watch out.** `/media` must `Path.resolve()` and check `is_relative_to(project_root)` —
  classic traversal hole otherwise. Jobs run in threads; FastAPI sync `def` endpoints are
  fine (threadpool).
  **Verify.** `pytest tests/test_server.py` — `TestClient` exercises every route with mocked
  services; includes traversal-attempt test (`../../etc/passwd` → 404).

- [ ] C2. Free-port + server boot helper: bind `('127.0.0.1', 0)` to find a port, pass to
  `uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=p, workers=1, log_level="warning"))`
  in a daemon thread; `wait_until_up(url, timeout=10)` via `urllib` poll.
  **Watch out.** Never `uvicorn.run` and never `reload`/`workers>1` — subprocess spawning
  breaks PyInstaller. Call `multiprocessing.freeze_support()` in `main()` first line.
  **Verify.** Manual: `./venv/bin/python3 -m app.main --server-only` serves on the printed
  URL and `curl` works (add that flag while developing).

#### Phase D — Frontend

- [ ] D1. `app/frontend/styles.css`: design tokens block **verbatim from the design brief**,
  then all component classes listed there, motion keyframes, focus-visible styles. Fonts:
  download Fraunces (400, 600, italic) + Karla (400, 500, 700) woff2 (latin subset) from
  Google Fonts, commit into `app/frontend/fonts/`, `@font-face` with local fallbacks.
  **Watch out.** One CSS file only; no preprocessors; no external CDN at runtime.
  **Verify.** Open `index.html` in a browser (even file://) — tokens render, buttons show
  `--shadow-pop`, fonts load or fall back gracefully.

- [ ] D2. `app/frontend/index.html` + `app.js`: the three screens exactly as in the design
  brief (Word / Voice / Bake), stepper, toasts, modal. `app.js` (~600 lines, vanilla):
  `state` object synced from `GET /api/state`; `render()` re-renders each screen's dynamic
  parts (rows table, voice select, inclusion list, estimate); `api(path, opts)` fetch
  wrapper with error→toast; `poll(jobId, onDone)` at 500 ms; file drop + input for import;
  `<audio>` playback of `/media/...` URLs and test-voice blob URLs.
  **Watch out.** All user-visible strings **verbatim from the microcopy list**. Number inputs
  send floats for gaps (`1.2` not `1`). Disable Generate/Bake buttons while a job runs.
  **Verify.** Run with `--server-only`, drive all three screens against a 5-row demo project
  with services mocked behind the real server; every flow reachable by click only.

- [ ] D3. Post-processing completeness on the Words screen (the user's open question —
  this is the answer): edit translation text (marks `stale` + toast *"Row {n} is stale —
  regenerate it."*), `↻ Regenerate` per variant, `+ Below` insert after row N, bottom
  "Add at the end" + "Add at row #N" forms, `↑/↓` reorder, `✕` delete (modal confirm),
  and **rebuild is instant/local** (Bake screen rebuild from cache). Recent projects list
  on Words screen when no project is open (folder paths from a tiny `recent.json` in the
  app data dir `~/.local/share/WordTape/`).
  **Verify.** Manual walkthrough: change one word → regenerate → rebuild; insert at row 3;
  delete row; reorder; close app; reopen project — all state intact.

#### Phase E — Desktop shell

- [ ] E1. `app/main.py`: `if __name__ == "__main__": multiprocessing.freeze_support(); main()`.
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

- [ ] F1. `build.sh`: (1) `./venv/bin/pip install -r requirements-dev.txt`; (2) fonts check
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

- [ ] F2. `build-docker.sh` (glibc fallback, Trap 2): same build inside
  `docker run --rm -v "$PWD":/src -w /src ubuntu:22.04` after
  `apt-get update && apt-get install -y python3 python3-venv python3-gi python3-gi-cairo
  gir1.2-webkit2-4.0 build-essential` + pip installs. Produces a glibc-2.35-linked binary
  that runs on older Zorin. Only needed if the Mint-built binary fails on Zorin.
  **Verify.** Script runs to `dist/WordTape` in the container (or document as untested
  fallback with exact commands if docker is unavailable — checked at execution time).

- [ ] F3. Key-in security note (one paragraph in README): the binary contains the Gemini
  API key and is recoverable with `strings`; acceptable for personal two-user use; do not
  upload the binary to public scanners/sharing; rotate the key in AI Studio if leaked;
  env var `GEMINI_API_KEY` overrides the baked key (useful after rotation).

#### Phase G — Docs & verification

- [ ] G1. README section **WordTape (desktop app)**: what it is, run from source
  (`./venv/bin/python3 -m app.main`), build (`./build.sh`), Zorin note (copy `dist/WordTape`;
  if `GLIBC_x.y not found` → `./build-docker.sh`), first-run flow (new project → import),
  screenshots optional. Update `requirements.txt`: add `fastapi`, `uvicorn`, `pywebview`,
  `imageio-ffmpeg`; `requirements-dev.txt` adds `pyinstaller`. Sync `AGENTS.md` (app layout
  + "no build step in frontend" + secrets convention).
  **Verify.** README commands all run as written.

- [ ] G2. Full end-to-end on the built binary (the real acceptance test):
  1. New project (de→id, variants ON). 2. Import a 10-word German `.txt`. 3. Translate →
  10 rows × up to 3 variants. 4. Test two voices. 5. Generate all (progress + cancel once,
  then resume). 6. Edit one translation → regenerate that one. 7. Insert a row at position 3
  and one at the end; delete one; reorder one. 8. Bake with defaults → estimate ≈ sum of
  clips×5 + gaps; play final.mp3: each translation 5× with audible repeat breaks, **no
  German in the track**. 9. Copy MP3 to a phone and confirm playback. 10. Close/reopen the
  project — everything persists.
  **Verify.** All 10 steps pass on Mint; user repeats steps 1–3 and 8 on Zorin.

- [ ] G3. `pytest tests/ -q` fully green; commit everything (message like
  `Add WordTape desktop app (pywebview + FastAPI) on executable-ui`); move finished items to
  `TODO-DONE.md`.

### Likely problems & pre-approved fixes

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | `import webview` fails or window never appears on a target machine | PyGObject/WebKit2GTK is a **system** package; PyInstaller can't bundle `gi` | build venv with `--system-site-packages`; README: `sudo apt install python3-gi python3-gi-cairo gir1.2-webkit2-4.0` (or `gir1.2-webkit2-4.1` on newer); app auto-falls back to system browser (E1) |
| 2 | `GLIBC_2.38 not found` on Zorin | binary built on newer glibc than target | `./build-docker.sh` (ubuntu:22.04 → glibc 2.35 covers Mint 22 + Zorin 17/18); check `ldd --version` on Zorin first |
| 3 | Frozen app: `FileNotFoundError` for frontend/ffmpeg | relative paths break under `--onefile` (`sys._MEIPASS`) | always `config.resource_path()`; `--add-data`/`--add-binary` flags exactly as in F1 |
| 4 | `ModuleNotFoundError: google.genai.*` only in frozen build | google-genai lazy-imports submodules | `--collect-all google.genai --collect-all httpx` (F1) |
| 5 | uvicorn crash/hang in frozen app | `uvicorn.run`/reload/workers spawn processes | `uvicorn.Server` in daemon thread, `workers=1`, no reload (C2); `freeze_support()` first line of `main` |
| 6 | CSV import produces 1 mangled column | European Excel: `;` delimiter + UTF-8 BOM | `utf-8-sig` + Sniffer + fallback retries `;`, `\t` (A3) |
| 7 | Audio cache files vanish/mismatch after reordering rows | filenames derived from position | stable random `row_id`/`variant_id` in filenames (A2) |
| 8 | Translations arrive as ```json fenced blob or truncated | model wraps/overruns JSON | `response_mime_type="application/json"`; strip fences; one "ONLY valid JSON" retry; batches of 25 (B1) |
| 9 | `400` on translation calls | `temperature`/`top_p` deprecated on 3.x | never set sampling params (B1) |
| 10 | `404 models/gemini-3.8-flash-lite is not found` | text-vs-TTS confusion (user hit this) | translation = `gemini-3.5-flash-lite`, TTS = `gemini-3.8-flash-*-tts`; constants in `config.py`; error messages name the constant |
| 11 | Webview blocks audio playback | autoplay policy | all playback triggered by button clicks; `<audio>` gets `controls`, never `autoplay` |
| 12 | `/media` serves files outside the project | path traversal | `resolve()` + `is_relative_to(project_root)` (C1) |
| 13 | Silences sound wrong / waveform offset | float byte math | integer sample counts only; golden test (B3) |
| 14 | Fonts missing in frozen build | woff2 not bundled | commit fonts to `app/frontend/fonts/`, `--add-data` includes them, fallback stacks anyway |
| 15 | Two jobs run concurrently and corrupt project.json | no job serialization | one job at a time, 409 (B4); project writes under a `threading.Lock` |
| 16 | `secrets.py` committed | generated file | `.gitignore` entry in F1; `git status` check in G3 |

### Follow-ups (out of scope)

- Undo/redo in the editor; multi-project management UI beyond "recent"; per-row voices;
  export to Anki/CSV; dark theme; Windows/macOS builds (PyInstaller can't cross-compile —
  needs one build per OS); auto-update.

### Definition of done

- [ ] All tasks A1–G3 checked with their `Verify` steps actually run.
- [ ] `pytest tests/ -q` green; `./dist/WordTape` passes the 10-step acceptance walk (G2).
- [ ] Binary runs on Linux Mint (this machine) and is handed to the user for a Zorin check.
- [ ] README/requirements/AGENTS.md in sync (repo convention); one clean commit on
  `executable-ui`; no secrets in `git show`.
- [ ] Finished items moved to `TODO-DONE.md`.
