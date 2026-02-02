# Google Cloud TTS Batch Generator (Indonesian)

This project allows you to generate high-quality Indonesian audio files from a text list using the Google Cloud Text-to-Speech API.

## 📋 Requirements

*   **Python 3.12+**
*   **Google Cloud Project** with the "Cloud Text-to-Speech API" enabled.
*   **Service Account JSON Key** saved as `service-account.json` in this directory.

## 🚀 Setup

1.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Credentials:**
    *   Place your Google Cloud Service Account JSON file in the project root and rename it to `service-account.json`.
    *   **Important:** Ensure `service-account.json` is ignored by git to protect your credentials. The `.gitignore` file included in this repo handles this.

## 🎙️ How to Run

### Basic Usage (Default Voice: id-ID-Wavenet-A)
```bash
./venv/bin/python3 batch_generate_audio.py
```

### Selecting a Specific Voice
Use the `--voice` argument to choose a different voice.

```bash
# Use the Male Wavenet voice
./venv/bin/python3 batch_generate_audio.py --voice id-ID-Wavenet-B
```

**Available Indonesian Voices:**

| Voice Name | Gender | Type | Style/Note |
| :--- | :--- | :--- | :--- |
| `id-ID-Wavenet-A` | Female | Wavenet | Natural, clear, feminine. (Default) |
| `id-ID-Wavenet-B` | Male | Wavenet | Natural, deep, masculine. |
| `id-ID-Wavenet-C` | Male | Wavenet | Natural, alternative masculine tone. |
| `id-ID-Wavenet-D` | Female | Wavenet | Natural, alternative feminine tone. |
| `id-ID-Standard-A` | Female | Standard | Concatenative, clear but less natural. |
| `id-ID-Standard-B` | Male | Standard | Concatenative, clear but less natural. |

## 📂 Output

*   Files are saved in the `output_audio` folder as `line_XXX.wav`.
*   The script skips existing files unless the `--force` flag is used.