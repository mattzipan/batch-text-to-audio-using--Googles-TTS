#!/usr/bin/env bash
# Build the WordTape desktop executable (Linux). Run from the repo root.
# Bakes GEMINI_API_KEY from .env into the binary (personal two-user tool).
set -euo pipefail

PY=./buildvenv/bin/python
if [ ! -x "$PY" ]; then
  echo "buildvenv missing; create it first:"
  echo "  python3 -m venv buildvenv --system-site-packages && ./buildvenv/bin/pip install -r requirements-dev.txt"
  exit 1
fi
$PY -m pip install -q -r requirements-dev.txt

# 1. Fonts must be vendored (committed in app/frontend/fonts).
if ! ls app/frontend/fonts/*.woff2 >/dev/null 2>&1; then
  echo "ERROR: app/frontend/fonts/*.woff2 missing."
  exit 1
fi

# 2. ffmpeg binary (static, via the imageio-ffmpeg wheel).
mkdir -p app/ffmpeg_bin
$PY -c "import imageio_ffmpeg, shutil; shutil.copy(imageio_ffmpeg.get_ffmpeg_exe(), 'app/ffmpeg_bin/ffmpeg')"
chmod +x app/ffmpeg_bin/ffmpeg
./app/ffmpeg_bin/ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libmp3lame \
  || { echo "ERROR: bundled ffmpeg lacks libmp3lame"; exit 1; }

# 3. API key -> app/secrets.py (gitignored, baked into the binary).
$PY - <<'EOF'
from dotenv import dotenv_values
key = (dotenv_values(".env").get("GEMINI_API_KEY") or "").strip()
if not key:
    raise SystemExit("ERROR: GEMINI_API_KEY missing from .env")
with open("app/secrets.py", "w") as f:
    f.write(f'API_KEY = "{key}"\n')
print("secrets.py written (gitignored, baked into the binary)")
EOF

# 4. PyInstaller onefile. gi/WebKit come from the SYSTEM (never bundled):
#    --exclude-module gi keeps PyInstaller's gi hooks from firing, which both
#    drops ~300k useless icon/theme files AND forces the frozen app to use the
#    system PyGObject (wired up at runtime by main.py's sys.path helper).
$PY -m PyInstaller --noconfirm --clean --onefile --name WordTape \
  --add-data "app/frontend:app/frontend" \
  --add-binary "app/ffmpeg_bin/ffmpeg:app/ffmpeg_bin" \
  --hidden-import webview.platforms.gtk \
  --hidden-import optparse \
  --exclude-module gi \
  --collect-all webview \
  --collect-all httpx \
  --collect-all google.genai \
  app/main.py

echo "OK: dist/WordTape"
./dist/WordTape --help 2>&1 | head -5 || true
