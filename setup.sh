#!/usr/bin/env bash
# One-time setup: installs build tools, builds llama.cpp for THIS cpu,
# and installs cloudflared. Safe to re-run; finished steps are skipped.
#   ./setup.sh            normal setup
#   ./setup.sh --update   pull latest llama.cpp and rebuild
set -euo pipefail
cd "$(dirname "$0")"

have() { command -v "$1" >/dev/null 2>&1; }
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
UPDATE=0; [ "${1:-}" = "--update" ] && UPDATE=1
JOBS="${JOBS:-2}"   # low on purpose: compiling with many jobs can run a 4 GB PC out of RAM

echo "==> Installing build tools"
if have apt-get; then
  $SUDO apt-get update -y >/dev/null
  $SUDO apt-get install -y git build-essential cmake curl ca-certificates >/dev/null
else
  echo "apt-get not found. Install git, cmake, a C++ compiler and curl manually."
fi

# ---- llama.cpp ----
if [ ! -d llama.cpp ]; then
  echo "==> Cloning llama.cpp"
  git clone --depth 1 https://github.com/ggml-org/llama.cpp.git llama.cpp
elif [ "$UPDATE" -eq 1 ]; then
  echo "==> Updating llama.cpp"
  git -C llama.cpp pull --ff-only
fi

BIN="llama.cpp/build/bin"
if [ -x "$BIN/llama-server" ] && [ -x "$BIN/llama-cli" ] && [ "$UPDATE" -eq 0 ]; then
  echo "==> llama.cpp already built, skipping (use --update to rebuild)"
else
  echo "==> Building llama.cpp with $JOBS jobs (this can take 10-30+ minutes on an old CPU)"
  cmake -S llama.cpp -B llama.cpp/build -DCMAKE_BUILD_TYPE=Release \
        -DGGML_NATIVE=ON -DLLAMA_CURL=OFF
  cmake --build llama.cpp/build --config Release -j"$JOBS" \
        --target llama-server llama-cli
fi

# ---- cloudflared ----
if have cloudflared; then
  echo "==> cloudflared already installed"
else
  case "$(uname -m)" in
    x86_64)  ARCH=amd64 ;;
    aarch64) ARCH=arm64 ;;
    armv7l)  ARCH=arm ;;
    *) echo "No cloudflared build for $(uname -m). Local chat/serve still work."; ARCH="" ;;
  esac
  if [ -n "$ARCH" ]; then
    echo "==> Installing cloudflared ($ARCH)"
    curl -fsSL -o /tmp/cloudflared \
      "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}"
    $SUDO install -m 755 /tmp/cloudflared /usr/local/bin/cloudflared
    rm -f /tmp/cloudflared
  fi
fi

[ -f .env ] || { cp .env.example .env; echo "==> Created .env"; }
mkdir -p models
chmod +x run.sh
echo "==> Done. Next: ./run.sh"
