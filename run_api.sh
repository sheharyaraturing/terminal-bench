#!/usr/bin/env bash
# Start the autoreviewer API + test UI.
#   ./run_api.sh            -> http://localhost:8000
#   PORT=9000 ./run_api.sh
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m uvicorn api.main:app --reload --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
