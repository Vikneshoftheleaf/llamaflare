#!/usr/bin/env bash
# Compatibility launcher for the cross-platform Python CLI.
set -euo pipefail
cd "$(dirname "$0")"
python3 model_server.py "$@"
