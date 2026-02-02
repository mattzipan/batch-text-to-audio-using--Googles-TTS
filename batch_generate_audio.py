import os
import time
import wave
import argparse
import re
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ClientError

# Load API key from .env file
load_dotenv()

# --- Configuration ---
API_KEY = os.getenv("GEMINI_API_KEY") 

# Input and Output
INPUT_FILE = "sentences.txt"
OUTPUT_DIR = "output_audio"
LANGUAGE_INSTRUCTION = "Indonesian"

# Model Configuration
MODEL_NAME = "gemini-2.5-flash-preview-tts" 
DEFAULT_VOICE = "Charon"

# Rate Limiting
# The free tier for TTS is approximately 3 requests per minute.
# We set a conservative delay to attempt to avoid hitting the limit.
DEFAULT_DELAY_SECONDS = 60 

def setup_client():
    if not API_KEY:
        print("Error: GEMINI_API_KEY not found in .env file.")
        return None
    return genai.Client(api_key=API_KEY)

def generate_audio_for_text(client, text, index, voice_name):
    """
    Generates audio for a single text entry using Gemini's native speech generation.
    Includes retry logic for rate limits.
    """
    max_retries = 10
    attempt = 0
    
    while attempt < max_retries:
        try:
            # Prompt designed for language learning clarity
            prompt = (
                f"Please read the following {LANGUAGE_INSTRUCTION} text aloud. "
                "Pronounce it slowly, clearly, and naturally like a native speaker "
                "helping a student learn the language:\n\n"
                f"'{text}'"
            )
            
            # Configure speech with the specific voice
            speech_cfg = types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name
                    )
                )
            )

            # Use the new client to request AUDIO modality
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=speech_cfg
                )
            )
            
            audio_data = None
            # In the new SDK, audio might be in parts with inline_data
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                        audio_data = part.inline_data.data
                        break
            
            if not audio_data:
                print(f"Warning: No audio data returned for line {index}.")
                return False

            # Save to file with WAV header
            output_path = Path(OUTPUT_DIR) / f"line_{index:03d}.wav"
            
            # PCM Settings for Gemini 2.5 Flash
            n_channels = 1
            sampwidth = 2  # 2 bytes = 16-bit
            framerate = 24000 # 24kHz
            
            with wave.open(str(output_path), "wb") as wav_file:
                wav_file.setnchannels(n_channels)
                wav_file.setsampwidth(sampwidth)
                wav_file.setframerate(framerate)
                wav_file.writeframes(audio_data)
            
            print(f"Generated: {output_path}")
            return True

        except ClientError as e:
            # Check for 429 Resource Exhausted
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                print(f"Rate limit hit for line {index}. analyzing delay...")
                
                # Try to extract the retry time from the error message
                # Message usually contains: "Please retry in 52.574752088s."
                match = re.search(r"retry in (\d+\.?\d*)s", str(e))
                if match:
                    wait_time = float(match.group(1)) + 10.0 # Add 10s buffer to be safe
                    print(f"API requested wait of {wait_time:.2f}s. Sleeping...")
                    time.sleep(wait_time)
                else:
                    # Fallback wait if we can't parse the specific time
                    fallback_wait = 70
                    print(f"Could not parse retry time. Sleeping for {fallback_wait}s...")
                    time.sleep(fallback_wait)
                
                attempt += 1
                continue # Retry the loop
            
            else:
                # Some other error happened
                print(f"Error processing line {index}: {e}")
                return False

        except Exception as e:
            print(f"Unexpected error processing line {index}: {e}")
            return False
            
    print(f"Failed to generate line {index} after {max_retries} attempts.")
    return False

def main():
    parser = argparse.ArgumentParser(description="Generate Indonesian audio from text file.")
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
        lines = f.readlines()

    print(f"Found {len(lines)} lines. Using voice: '{args.voice}'. Starting generation...")
    print(f"Note: To respect free tier limits (~3 req/min), we will wait {DEFAULT_DELAY_SECONDS}s between requests.")

    # Process each line
    for i, line in enumerate(lines):
        text = line.strip()
        if not text: continue
        
        index = i + 1
        output_path = output_dir_path / f"line_{index:03d}.wav"
        
        if output_path.exists() and not args.force:
            print(f"Skipping ({index}/{len(lines)}): {text[:30]}... (File already exists)")
            continue
        
        print(f"Processing ({index}/{len(lines)}): {text[:30]}...")
        success = generate_audio_for_text(client, text, index, args.voice)
        
        if success:
            # Standard rate limit waiting
            time.sleep(DEFAULT_DELAY_SECONDS) 
        else:
            print("Skipping/Failed...")

    print("Batch processing complete.")

if __name__ == "__main__":
    main()