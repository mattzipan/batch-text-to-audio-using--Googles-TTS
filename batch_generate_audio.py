import os
import time
import argparse
from pathlib import Path
from google.cloud import texttospeech

# --- Configuration ---
SERVICE_ACCOUNT_FILE = "service-account.json"
INPUT_FILE = "sentences.txt"
OUTPUT_DIR = "output_audio"

# Default Voice: Neural2 is generally the highest quality
# Other options: id-ID-Wavenet-A, id-ID-Standard-A
DEFAULT_VOICE = "id-ID-Wavenet-A"

def setup_client():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        print(f"Error: {SERVICE_ACCOUNT_FILE} not found.")
        return None
    try:
        return texttospeech.TextToSpeechClient.from_service_account_json(SERVICE_ACCOUNT_FILE)
    except Exception as e:
        print(f"Error initializing Google Cloud TTS client: {e}")
        return None

def generate_audio_for_text(client, text, index, voice_name):
    """
    Generates audio for a single text entry using Google Cloud TTS.
    """
    try:
        synthesis_input = texttospeech.SynthesisInput(text=text)

        # Build the voice request
        # Extract language code from voice name (e.g., 'id-ID' from 'id-ID-Neural2-A')
        language_code = "-".join(voice_name.split("-")[:2])
        
        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name
        )

        # Select the type of audio file (LINEAR16 = WAV)
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=24000
        )

        # Perform the text-to-speech request
        response = client.synthesize_speech(
            input=synthesis_input, 
            voice=voice, 
            audio_config=audio_config
        )

        # Save to file
        output_path = Path(OUTPUT_DIR) / f"line_{index:03d}.wav"
        with open(output_path, "wb") as out:
            out.write(response.audio_content)
        
        print(f"Generated: {output_path}")
        return True

    except Exception as e:
        print(f"Error processing line {index}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Generate Indonesian audio using Google Cloud TTS.")
    parser.add_argument("--voice", type=str, default=DEFAULT_VOICE, help=f"Voice name (default: {DEFAULT_VOICE})")
    parser.add_argument("--force", action="store_true", help="Overwrite existing audio files")
    args = parser.parse_args()

    client = setup_client()
    if not client:
        return

    # Create output directory
    output_dir_path = Path(OUTPUT_DIR)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    # Read Text File
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found.")
        return

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]

    print(f"Found {len(lines)} lines. Using voice: '{args.voice}'.")
    print("Starting generation (Cloud TTS - no delay)...")

    start_time = time.time()
    success_count = 0

    # Process each line
    for i, text in enumerate(lines):
        index = i + 1
        output_path = output_dir_path / f"line_{index:03d}.wav"
        
        if output_path.exists() and not args.force:
            print(f"Skipping ({index}/{len(lines)}): {text[:30]}... (File already exists)")
            continue
        
        print(f"Processing ({index}/{len(lines)}): {text[:30]}...")
        if generate_audio_for_text(client, text, index, args.voice):
            success_count += 1
            # Tiny sleep to prevent flooding, though Cloud TTS handles 1000 RPM
            time.sleep(0.1) 
        else:
            print(f"Failed to generate line {index}")

    end_time = time.time()
    duration = end_time - start_time
    print(f"\nBatch processing complete.")
    print(f"Successfully generated {success_count} files in {duration:.2f} seconds.")

if __name__ == "__main__":
    main()
