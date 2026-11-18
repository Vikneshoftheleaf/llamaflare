#!/usr/bin/env bash
# One-time setup for Linux and macOS.
set -euo pipefail
cd "$(dirname "$0")"

have() { command -v "$1" >/dev/null 2>&1; }
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
UPDATE=0
for arg in "$@"; do [ "$arg" = "--update" ] && UPDATE=1; done
JOBS="${JOBS:-2}"

echo "==> Installing build tools"
if have apt-get; then
  $SUDO apt-get update -y >/dev/null
  $SUDO apt-get install -y git build-essential cmake curl ca-certificates python3 >/dev/null
elif have dnf; then
  $SUDO dnf install -y git gcc gcc-c++ cmake curl python3
elif have pacman; then
  $SUDO pacman -Sy --needed --noconfirm git base-devel cmake curl python
elif have brew; then
  brew install git cmake curl python
else
  echo "Install git, cmake, a C/C++ compiler and Python 3 manually."
fi

have git || { echo "Git is required."; exit 1; }
have cmake || { echo "CMake is required."; exit 1; }
if ! have python3 && ! have python; then
  echo "Python 3 is required."
  exit 1
fi

if [ ! -d llama.cpp ]; then
  echo "==> Cloning llama.cpp"
  git clone --depth 1 https://github.com/ggml-org/llama.cpp.git llama.cpp
elif [ "$UPDATE" -eq 1 ]; then
  echo "==> Updating llama.cpp"
  git -C llama.cpp pull --ff-only
fi

BIN="llama.cpp/build/bin"
if [ -x "$BIN/llama-server" ] && [ -x "$BIN/llama-cli" ] && [ "$UPDATE" -eq 0 ]; then
  echo "==> llama.cpp already built, skipping"
else
  echo "==> Building llama.cpp with $JOBS jobs"
  cmake -S llama.cpp -B llama.cpp/build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON -DLLAMA_CURL=OFF
  cmake --build llama.cpp/build --config Release -j"$JOBS" --target llama-server llama-cli
fi

if ! have cloudflared; then
  case "$(uname -m)" in
    x86_64|amd64) ARCH=amd64 ;;
    arm64|aarch64) ARCH=arm64 ;;
    armv7l) ARCH=arm ;;
    *) echo "No cloudflared build for $(uname -m). Local chat/serve still work."; ARCH="" ;;
  esac
  if [ -n "$ARCH" ]; then
    OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
    case "$OS" in darwin) OS=darwin ;; linux) OS=linux ;; *) OS="" ;; esac
    if [ -n "$OS" ]; then
      echo "==> Installing cloudflared ($OS-$ARCH)"
      curl -fsSL -o /tmp/cloudflared "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-$OS-$ARCH"
      $SUDO install -m 755 /tmp/cloudflared /usr/local/bin/cloudflared
      rm -f /tmp/cloudflared
    fi
  fi
fi

[ -f .env ] || { cp .env.example .env; echo "==> Created .env"; }
mkdir -p models
chmod +x run.sh model_server.py
echo "==> Done. Run: ./run.sh"
