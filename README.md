# Batch Text-to-Audio (Gemini TTS)

Generate one audio file per line from a text list, using Google's Gemini text-to-speech models
(`gemini-3.8-flash-lite-tts` by default, `gemini-3.8-flash-tts` for maximum quality).

Multi-language by design with Indonesian-first defaults: the sample `sentences.txt` is Indonesian,
but nothing hardcodes any language — pass `--language` (e.g. `id-ID`) or let Gemini auto-detect.

## 📋 Requirements

*   **Python 3.12+**
*   **Gemini API key** (free from [Google AI Studio](https://aistudio.google.com/apikey)).
    Set **only one** of `GEMINI_API_KEY` / `GOOGLE_API_KEY` — if both are set, `GOOGLE_API_KEY` wins.
*   Optional, legacy path only: a **Google Cloud project** with "Cloud Text-to-Speech API" enabled
    plus a **service account key** (see `--backend cloud-tts` below).

> **Security:** never commit API keys or credentials. `.env` and `service-account.json` are
> gitignored. No `.env.example` is shipped (by design — see git history); create `.env` yourself
> as shown in Setup.

## 🚀 Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements-dev.txt
printf 'GEMINI_API_KEY=\n' > .env   # then put your key in .env (no .env.example is shipped, by design)
```

For tests only, `./venv/bin/pip install pytest` is enough on top of `requirements.txt`.

## 🎙️ How to Run

```bash
# Basic run: sentences.txt -> output_audio/line_001.wav, ...
./venv/bin/python3 batch_generate_audio.py

# Higher quality flagship model
./venv/bin/python3 batch_generate_audio.py --model gemini-3.8-flash-tts

# Different voice / language / delivery style
./venv/bin/python3 batch_generate_audio.py --voice Aoede --language id-ID --style "warm and friendly"

# Discover voices for a language
./venv/bin/python3 batch_generate_audio.py --list-voices --language id-ID

# Regenerate everything even if files exist
./venv/bin/python3 batch_generate_audio.py --force
```

| Flag | Default | Notes |
| :--- | :--- | :--- |
| `--backend` | `gemini` | `gemini` or `cloud-tts` (legacy Google Cloud TTS fallback) |
| `--model` | `gemini-3.8-flash-lite-tts` | or `gemini-3.8-flash-tts`. Gemini backend only |
| `--voice` | `Kore` (gemini) / `id-ID-Wavenet-A` (cloud-tts) | Prebuilt Gemini voice name, or a Cloud TTS voice name |
| `--language` | auto-detect | BCP-47 code (`id-ID`). Used for voice lookup/validation |
| `--style` | none | Delivery style, e.g. `"warm and friendly"`. Gemini only |
| `--list-voices` | off | Print voices and exit (no input file needed) |
| `--input` / `--output-dir` | `sentences.txt` / `output_audio` | Input list and output folder |
| `--force` | off | Overwrite existing files |

Notes:

*   Gemini treats your text as a **verbatim transcript**: style goes in `--style`, never in the
    text itself. Inline tags like `<laugh>` and `<short pause>` are spoken events and pass through.
*   Existing output files are **skipped** unless `--force` is used — re-running resumes for free.
*   Ctrl-C cancels cleanly (exit 130); re-run to resume.
*   Per-line failures are reported and the run continues; auth failures abort the whole run.

### Legacy backend: `--backend cloud-tts`

Keeps the original Google Cloud TTS path. Requires `service-account.json` in the project root
(a GCP service-account key with Cloud Text-to-Speech API enabled). `--model` and `--style` are
rejected on this backend.

**Available Indonesian voices (cloud-tts):**

| Voice Name | Gender | Type | Style/Note |
| :--- | :--- | :--- | :--- |
| `id-ID-Wavenet-A` | Female | Wavenet | Natural, clear, feminine. (Default for cloud-tts) |
| `id-ID-Wavenet-B` | Male | Wavenet | Natural, deep, masculine. |
| `id-ID-Wavenet-C` | Male | Wavenet | Natural, alternative masculine tone. |
| `id-ID-Wavenet-D` | Female | Wavenet | Natural, alternative feminine tone. |
| `id-ID-Standard-A` | Female | Standard | Concatenative, clear but less natural. |
| `id-ID-Standard-B` | Male | Standard | Concatenative, clear but less natural. |

```bash
./venv/bin/python3 batch_generate_audio.py --backend cloud-tts --voice id-ID-Wavenet-B
```

## 📝 Input File Format

Plain text (`.txt`), UTF-8, one sentence per line. Blank lines are skipped:

```
Halo! Apa kabar?
Nama saya Matthias.
...
```

## 📂 Output

*   `output_audio/line_001.wav`, `line_002.wav`, ... — 1-based input line numbers, never renumbered.
*   Format: 24 kHz mono 16-bit WAV.

## 💰 Cost note

`gemini-3.8-flash-lite-tts` costs ≈ $0.0015 per 10 s of audio at current intro pricing
(pricing doubles 2027-01-01). A 76-sentence list costs a fraction of a cent.

## 🧪 Development

```bash
./venv/bin/python3 -m pytest tests/ -q
```

Tests use mocked API clients — no network, no key needed. See `TODO.md` for the roadmap and
`AGENTS.md` for project conventions.

## 🖥️ WordTape (desktop app)

WordTape turns a word list (`.txt`) or word+translation table (`.csv`) into a repeating
"listen and repeat" drill track (`final.mp3`): pick source/target languages, auto-translate
with Gemini, test voices, generate per-translation audio, then bake one track where every
translation plays 5× with silence breaks. Finished tracks are exported to the system **Music**
folder (`~/Music/WordTape/<project>/`; fallback `output/<project>/` next to the executable).
Working data lives in `projects/` next to the executable (or the repo root in dev) so nothing is
written outside the app folder. Projects persist so single
translations can be fixed and the track rebuilt later.

Import words by dropping a `.txt`/`.csv` anywhere on the app window (or click the import zone
to pick a file). With **Also make formal + informal versions** enabled, translate also returns
formal/informal variants — always alternative renderings **in the target language**, never in
the source language (the ⇄ row action re-translates a row and replaces its variants).

### Settings (⚙ in the top bar)

*   **Gemini API key** — replaceable per machine, no rebuild needed. Saved to
    `~/.local/share/WordTape/settings.json` (`$XDG_DATA_HOME/WordTape/settings.json`, file mode
    `0600`, dir `0700`, gitignored) and applied immediately — Translate/TTS pick it up without a
    restart. Resolution order: **Settings key → `GEMINI_API_KEY` env → key baked in at build
    time** (`app/secrets.py`). `GOOGLE_API_KEY` is ignored by the app (the CLI above still
    honors it). "Remove key" clears the saved key and falls back to env/baked. The key is never
    shown back in full — only its last 4 characters.
*   **Output folder** — where finished tracks land (default `~/Music/WordTape/<project>/`,
    fallback `output/<project>/` next to the executable). An absolute custom root overrides both
    the default and `WORDTAPE_EXPORT_DIR`; "Reset to default" restores the default chain. Saved
    tracks are never migrated — old exports stay where they were written.

### Costs (estimates)

Every billable action (Translate, Bake/Generate, voice sample) shows a local **estimate** —
`(~$X est.)` in the completion toast — computed as the response's `usageMetadata` token counts
× the published Standard-tier price table (`app/costs.py`). These are **estimates only**: the
Gemini API reports tokens, never dollars, so authoritative spend lives in **AI Studio Billing**.
The ⚙ Settings → *Costs (estimates)* card accumulates the same estimates per calendar month
(current month line + a `Month | Translate | Voice | Total | Calls` history table) in a local
ledger at `~/.local/share/WordTape/costs.json` (`$XDG_DATA_HOME/WordTape/costs.json`,
gitignored; no API keys are ever stored in it). TTS prices are **introductory through
Dec 31, 2026 and double on Jan 1, 2027** — the table applies that doubling automatically;
retry calls are counted too. Unknown usage never renders `$0.00` — the suffix and the estimate
simply stay absent.

### Run from source

```bash
./buildvenv/bin/python3 -m app.main            # native window (needs system WebKit)
./buildvenv/bin/python3 -m app.main --server-only  # print URL, use any browser
```

The dev venv needs system packages visible: create it with
`python3 -m venv buildvenv --system-site-packages` and install
`requirements-dev.txt`.

The native window's minimum size is 640×400, so tiling shortcuts (Super+Left/Right,
drag-to-edge) can snap it to half of a 1080p/HiDPI-scaled screen. Below 900px the UI
collapses to one column and the rows table scrolls horizontally instead of reflowing.

### Build the executable

```bash
./build.sh   # reads GEMINI_API_KEY from .env, bakes it in, writes dist/WordTape
```

`build.sh` copies a static ffmpeg (via `imageio-ffmpeg`) and your API key
(`app/secrets.py`, gitignored) into a ~110 MB onefile binary. The key is recoverable
from the binary with `strings` — acceptable for personal two-user use; do **not** upload
the binary anywhere public, and rotate the key in AI Studio if it leaks. The baked key is
only the fallback: each machine can override it with its own key in **⚙ Settings** (see
Settings above), applied without a rebuild.

Copy `dist/WordTape` to the other machine and run it. One build covers Linux Mint and
Zorin 18 (both Ubuntu 24.04-based, same glibc). If it ever fails with
`GLIBC_x.y not found` on an older distro, use `./build-docker.sh` (untested Ubuntu 22.04
container fallback).

If the native window can't start (missing WebKit), the app automatically falls back to
opening the system browser at its local URL. For the native window you need
`python3-gi`, `python3-gi-cairo` and `gir1.2-webkit2-4.1` installed (present by default
on Mint; on Zorin: `sudo apt install python3-gi python3-gi-cairo gir1.2-webkit2-4.1`).
