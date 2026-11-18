#!/usr/bin/env bash
# CLI chat, local API server, or public Cloudflare tunnel for llama.cpp.
# Downloads the model only if it is missing (resumes partial downloads).
set -euo pipefail
cd "$(dirname "$0")"

# ---- defaults, overridden by .env, then by flags ----
MODEL="llama3.2-1b"
PORT=8080
CTX=2048
THREADS=""
API_KEY=""
MODE="chat"        # chat | serve | tunnel
[ -f .env ] && set -a && . ./.env && set +a

BIN="llama.cpp/build/bin"
STATE=".state"; mkdir -p "$STATE" models
SERVER_PID="$STATE/server.pid"; SERVER_LOG="$STATE/server.log"
TUNNEL_PID="$STATE/tunnel.pid"; TUNNEL_LOG="$STATE/tunnel.log"

usage() {
  cat <<USAGE
Usage: ./run.sh [options]
  -m, --model NAME|PATH|URL   model key from models.conf, a .gguf file, or a download URL
  -c, --chat                  interactive chat in the terminal (default)
  -s, --serve                 local API + web UI at http://127.0.0.1:$PORT
  -t, --tunnel                serve and expose publicly via Cloudflare
      --ctx N                 context size (default $CTX; lower = less RAM)
      --threads N             CPU threads (default: physical cores)
      --port N                server port (default $PORT)
      --list                  list models in models.conf
      --stop                  stop server and tunnel
  -h, --help                  this help
USAGE
}

list_models() { echo "Available models (models.conf):"; awk -F'|' '!/^#/ && NF>=3 {printf "  %-16s %s\n",$1,$2}' models.conf; }

stop_all() {
  for f in "$TUNNEL_PID" "$SERVER_PID"; do
    if [ -f "$f" ]; then kill "$(cat "$f")" 2>/dev/null || true; rm -f "$f"; fi
  done
  echo "Stopped server and tunnel."
}

while [ $# -gt 0 ]; do
  case "$1" in
    -m|--model)   MODEL="$2"; shift 2 ;;
    -c|--chat)    MODE="chat"; shift ;;
    -s|--serve)   MODE="serve"; shift ;;
    -t|--tunnel)  MODE="tunnel"; shift ;;
    --ctx)        CTX="$2"; shift 2 ;;
    --threads)    THREADS="$2"; shift 2 ;;
    --port)       PORT="$2"; shift 2 ;;
    --list)       list_models; exit 0 ;;
    --stop)       stop_all; exit 0 ;;
    -h|--help)    usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 1 ;;
  esac
done

[ -x "$BIN/llama-cli" ] && [ -x "$BIN/llama-server" ] || { echo "llama.cpp not built. Run ./setup.sh first."; exit 1; }

# default threads = physical cores (hyperthreads rarely help inference)
if [ -z "$THREADS" ]; then
  THREADS=$(lscpu -p=core,socket 2>/dev/null | grep -v '^#' | sort -u | wc -l)
  [ "${THREADS:-0}" -ge 1 ] || THREADS=$(nproc)
fi

# ---- resolve + download model if missing ----
resolve_model() {
  local m="$1" url="" file=""
  if [ -f "$m" ]; then MODEL_PATH="$m"; echo "==> Using local file $m"; return; fi
  if [[ "$m" =~ ^https?:// ]]; then
    url="$m"; file="models/$(basename "${m%%\?*}")"
  else
    local line; line=$(awk -F'|' -v k="$m" '!/^#/ && $1==k {print; exit}' models.conf)
    [ -n "$line" ] || { echo "Unknown model '$m'."; list_models; exit 1; }
    file="models/$(echo "$line" | cut -d'|' -f2)"
    url=$(echo "$line" | cut -d'|' -f3)
  fi
  MODEL_PATH="$file"
  if [ -s "$file" ] && [ ! -f "$file.part" ]; then
    echo "==> Model already downloaded: $file"
  else
    echo "==> Downloading model (resumes if interrupted)"
    curl -fL -C - --retry 3 --progress-bar -o "$file.part" "$url" \
      || { echo "Download failed. Check the URL in models.conf."; exit 1; }
    mv "$file.part" "$file"
  fi
}
resolve_model "$MODEL"

# ---- chat mode: no server needed ----
if [ "$MODE" = "chat" ]; then
  exec "$BIN/llama-cli" -m "$MODEL_PATH" -c "$CTX" -t "$THREADS" -cnv
fi

# ---- API key (always for tunnel, optional for local serve) ----
if [ "$MODE" = "tunnel" ] && [ -z "$API_KEY" ]; then
  API_KEY=$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')
  echo "API_KEY=$API_KEY" >> .env
  echo "==> Generated an API key and saved it in .env"
fi

health() { curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; }

if health; then
  echo "==> Server already running on port $PORT (run ./run.sh --stop first to change model/settings)"
else
  echo "==> Starting llama-server (threads=$THREADS ctx=$CTX)"
  nohup "$BIN/llama-server" -m "$MODEL_PATH" -c "$CTX" -t "$THREADS" -np 1 \
    --host 127.0.0.1 --port "$PORT" ${API_KEY:+--api-key "$API_KEY"} \
    >"$SERVER_LOG" 2>&1 &
  echo $! >"$SERVER_PID"
  echo "==> Loading model (can take a minute on an old CPU)..."
  for _ in $(seq 1 180); do
    health && break
    kill -0 "$(cat "$SERVER_PID")" 2>/dev/null || { echo "Server exited. See $SERVER_LOG"; exit 1; }
    sleep 1
  done
  health || { echo "Server not ready. See $SERVER_LOG"; exit 1; }
fi

KEYHDR=""; [ -n "$API_KEY" ] && KEYHDR="-H 'Authorization: Bearer $API_KEY' "
CURL_BODY="-H 'Content-Type: application/json' -d '{\"messages\":[{\"role\":\"user\",\"content\":\"Hi\"}]}'"

if [ "$MODE" = "serve" ]; then
  echo
  echo "Web UI:  http://127.0.0.1:$PORT"
  echo "Test:    curl http://127.0.0.1:$PORT/v1/chat/completions $KEYHDR$CURL_BODY"
  exit 0
fi

# ---- tunnel mode ----
command -v cloudflared >/dev/null || { echo "cloudflared not found. Run ./setup.sh first."; exit 1; }
if [ -f "$TUNNEL_PID" ] && kill -0 "$(cat "$TUNNEL_PID")" 2>/dev/null; then
  echo "==> Tunnel already running"
else
  : >"$TUNNEL_LOG"
  nohup cloudflared tunnel --url "http://127.0.0.1:$PORT" >"$TUNNEL_LOG" 2>&1 &
  echo $! >"$TUNNEL_PID"
fi
echo "==> Waiting for tunnel URL..."
URL=""
for _ in $(seq 1 40); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | head -n1 || true)
  [ -n "$URL" ] && break; sleep 1
done
[ -n "$URL" ] || { echo "No URL yet. See $TUNNEL_LOG"; exit 1; }

echo
echo "Public URL: $URL"
echo "API key:    $API_KEY"
echo "Test:       curl $URL/v1/chat/completions $KEYHDR$CURL_BODY"
echo "The API needs the key; the web UI page loads but asks for the key in its settings."
echo "Stop everything with: ./run.sh --stop"
