#!/usr/bin/env bash
set -euo pipefail
export PATH="/root/.local/bin:${PATH}"
WORKSPACE="${PWD}"
cd /workspace
uv run python /solution/solve.py --workspace "${WORKSPACE}"
echo "Done!"
