# Gemini TTS Batch Generator (Indonesian)

This project allows you to generate high-quality Indonesian audio files from a text list using Google's Gemini 2.5 Flash API. It is designed for language learners who want native-like pronunciation for study materials.

## 📋 Requirements

*   **Python 3.12+**
*   **Google Gemini API Key** (Free tier available at [aistudio.google.com](https://aistudio.google.com))

## 🚀 Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/mattzipan/batch-text-to-audio-using--Googles-TTS.git
    cd batch-text-to-audio-using--Googles-TTS
    ```

2.  **Set up a Virtual Environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure API Key:**
    *   Rename `.env.example` to `.env`:
        ```bash
        cp .env.example .env
        ```
    *   Open `.env` and paste your Google Gemini API key:
        ```text
        GEMINI_API_KEY=AIzaSy...YourKeyHere...
        ```

## 📝 Input File Format

Create a file named **`sentences.txt`** in the project directory.
*   **Format:** Plain text.
*   **Structure:** One sentence per line.
*   **Encoding:** UTF-8 (recommended for special characters).

**Example `sentences.txt`:**
```text
Selamat pagi, apa kabar?
Saya ingin membeli dua nasi goreng.
Di mana kamar mandi?
```

## 🎙️ How to Run

Ensure your virtual environment is active, then run the script:

### Basic Usage
```bash
python batch_generate_audio.py
```
*Default Voice: Charon (Deep, Informative)*

### Selecting a Specific Voice
You can change the voice using the `--voice` argument.

```bash
# Use the "Kore" voice (Firm tone)
python batch_generate_audio.py --voice Kore

# Use the "Puck" voice (Upbeat tone)
python batch_generate_audio.py --voice Puck
```

**Common Voice Options:**
*   `Charon` (Deep, Informative) - *Default*
*   `Kore` (Firm, Clear)
*   `Puck` (Upbeat, Energetic)
*   `Fenrir` (Excitable)
*   `Aoede` (Breezy)

### Overwriting Existing Files
By default, the script **skips** generating audio for lines that already have a corresponding file in the `output_audio` folder. To force regeneration, use the `--force` flag.

```bash
python batch_generate_audio.py --force
```

## 📂 Output

*   The script creates a folder named **`output_audio`**.
*   Audio files are saved as `.wav` files (24kHz, 16-bit Mono).
*   Files are numbered sequentially corresponding to the line number in your text file (e.g., `line_001.wav`, `line_002.wav`).

## ⚠️ Notes

*   **Rate Limits:** The script includes a **60-second pause** between requests to respect the free tier rate limits (approx. 3 requests/minute).
*   **File Skipping:** As mentioned, existing files are skipped unless `--force` is used.