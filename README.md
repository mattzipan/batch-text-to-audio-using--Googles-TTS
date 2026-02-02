# Gemini TTS Batch Generator (Indonesian)

This project allows you to generate high-quality Indonesian audio files from a text list using Google's Gemini 2.5 Flash API. It is designed for language learners who want native-like pronunciation for study materials.

## 📋 Requirements

*   **Python 3.12+** (Installed on your system)
*   **Google Gemini API Key** (Free tier available at [aistudio.google.com](https://aistudio.google.com))

## 🚀 Setup

1.  **Navigate to the project directory:**
    ```bash
    cd /home/choppersmith/Code/tts
    ```

2.  **Create a Virtual Environment (if not already active):**
    ```bash
    # Create the environment
    python3 -m venv venv

    # Activate it
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install google-genai python-dotenv
    ```

4.  **Set your API Key:**
    *   Open (or create) the `.env` file in this directory.
    *   Add your key:
        ```bash
        GEMINI_API_KEY=AIzaSy...YourKeyHere...
        ```

## 📝 Input File Format

Create a file named **`sentences.txt`** in the same directory.
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

### Basic Usage (Default Voice: Charon)
Run the script using the Python interpreter in your virtual environment:

```bash
# Ensure you are in /home/choppersmith/Code/tts/
./venv/bin/python3 batch_generate_audio.py
```

### Selecting a Specific Voice
You can change the voice using the `--voice` argument.

```bash
# Use the "Kore" voice (Firm tone)
./venv/bin/python3 batch_generate_audio.py --voice Kore

# Use the "Puck" voice (Upbeat tone)
./venv/bin/python3 batch_generate_audio.py --voice Puck
```

### Overwriting Existing Files
By default, the script skips lines if the corresponding audio file already exists. To force regeneration, use the `--force` flag.

```bash
./venv/bin/python3 batch_generate_audio.py --force
```

**Common Voice Options:**
*   `Charon` (Deep, Informative) - *Default*
*   `Kore` (Firm, Clear)
*   `Puck` (Upbeat, Energetic)
*   `Fenrir` (Excitable)
*   `Aoede` (Breezy)

## 📂 Output

*   The script creates a folder named **`output_audio`**.
*   Audio files are saved as `.wav` files (24kHz, 16-bit Mono).
*   Files are numbered sequentially corresponding to the line number in your text file (e.g., `line_001.wav`, `line_002.wav`).

## ⚠️ Notes

*   **Rate Limits:** The script includes a **60-second pause** between requests to respect the free tier rate limits (approx. 3 requests/minute).
*   **File Skipping:** By default, the script **skips** generating audio for lines that already have a corresponding file in the `output_audio` folder. Use the `--force` flag to overwrite them.
