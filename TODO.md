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

## Spec: WordTape fixes batch 2 — UX polish, settings, layout (planned 2026-10-11)

Status: **planned, not started**. 10 sub-specs (F1–F10) covering 11 user items
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
