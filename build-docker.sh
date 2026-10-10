#!/usr/bin/env bash
# Fallback build for older glibc targets (e.g. Ubuntu 22.04-based distros).
# NOT needed for Mint 22 / Zorin 18 (same glibc 2.39 — use ./build.sh there).
# Untested here (no docker on the build machine); kept as a documented fallback.
# Usage: ./build-docker.sh   (reads .env from the repo root, writes dist/WordTape)
set -euo pipefail

docker run --rm \
  -v "$PWD":/src -w /src \
  ubuntu:22.04 bash -c '
    set -euo pipefail
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3 python3-venv python3-gi python3-gi-cairo \
      gir1.2-webkit2-4.0 build-essential curl ca-certificates
    python3 -m venv /opt/buildvenv --system-site-packages
    /opt/buildvenv/bin/pip install -q -r requirements-dev.txt
    ln -sfn /opt/buildvenv buildvenv
    ./build.sh
  '

echo "OK: dist/WordTape (glibc 2.35-linked)"
