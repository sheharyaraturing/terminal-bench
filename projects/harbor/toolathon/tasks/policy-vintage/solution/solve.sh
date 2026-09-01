#!/usr/bin/env bash
set -euo pipefail
export PATH="/root/.local/bin:${PATH}"

# setup.sh links /app at the agent workspace and blocks the healthcheck until
# the tool gateway answers, so both are in place by the time this runs. The
# tools are handed the resolved path rather than the symlink.
WORKSPACE="$(readlink -f /app)"

cd /workspace
uv run python /solution/oracle_runner.py --workspace "${WORKSPACE}"
echo "Done!"
