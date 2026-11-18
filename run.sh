#!/usr/bin/env bash
# Compatibility launcher for the cross-platform Python CLI.
set -euo pipefail
cd "$(dirname "$0")"
if command -v python3 >/dev/null 2>&1; then
  exec python3 model_server.py "$@"
elif command -v python >/dev/null 2>&1; then
  exec python model_server.py "$@"
else
  echo "Python 3 was not found. Run ./setup.sh first."
  exit 1
fi
