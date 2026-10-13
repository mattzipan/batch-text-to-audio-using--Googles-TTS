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

Status: **complete (2026-10-10)** — all 19 tasks finished and verified (113 mocked tests
green; live E2E on the built binary: 23 acceptance checks incl. byte-exact track layout;
native WebKit window confirmed rendering; MP3 valid). Finished items moved to TODO-DONE.md.
Purpose: a desktop executable for two users (personal, no auth, API key baked in) that turns
a word list into a repeating "listen and repeat" drill track.

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

All 19 tasks (A1–G3) completed 2026-10-10 — moved to TODO-DONE.md.

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

All criteria met 2026-10-10 — moved to TODO-DONE.md.

---

---

## Spec: WordTape fixes batch 2 — UX polish, settings, layout

Status: **complete (2026-10-11)**. All 10 sub-specs (F1–F10) implemented and
verified (183 mocked tests green; browser click-through of choice cards, toasts,
clickable switches, chips, Settings screen, tiling at 700px). Finished items
moved to [TODO-DONE.md](TODO-DONE.md).

---

## Spec: WordTape cost estimates — per-call toasts + monthly ledger

Status: **complete (2026-10-11)**. F11 (per-call `(~$X est.)` toasts) and F12
(local monthly ledger + Settings costs card) implemented and verified. Finished
items moved to [TODO-DONE.md](TODO-DONE.md).

### Verdict (kept for reference)

- The Gemini API (`generate_content`) returns **no dollar cost field** — only
  `response.usage_metadata` token counts. No billing API is readable with just
  `GEMINI_API_KEY` (Cloud Billing needs GCP OAuth + IAM). Authoritative spend
  lives in AI Studio Billing / Cloud Console only.
- Everything shown in the UI is labeled `est.` — computed locally as
  usageMetadata × Standard-tier pricing table (`app/costs.py`, which also
  handles the TTS introductory-pricing doubling on 2027-01-01). Ledger:
  `app/cost_ledger.py` (`~/.local/share/WordTape/costs.json`).

---

## Spec: WordTape fixes batch 3 — drag-n-drop import, target-language synonyms

Status: **complete (2026-10-13)**. B1 (drag-n-drop import) and B2 (target-language synonyms) implemented and verified (188 mocked tests green; browser click-through of drop/import, uri-list fallback, per-row ⇄ re-translate, updated microcopy). Finished items moved to [TODO-DONE.md](TODO-DONE.md).

---
