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
