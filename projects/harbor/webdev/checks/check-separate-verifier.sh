#!/usr/bin/env bash
# OVERRIDE of the repo-root common check-separate-verifier.sh — a DISPATCH,
# not a waiver.
#
# The two task shapes genuinely differ here, so a single answer is wrong:
#
#   dimensions (current format) grades in its own container built from
#   tests/Dockerfile. The common check's requirements all apply, so this
#   override runs it rather than reimplementing it.
#
#   browser-rubric (earlier format) grades in the shared agent container on
#   purpose: the verifier starts the agent's own app, in place, with the
#   node_modules the agent installed. A separate container would have to
#   rebuild and re-host the delivered app to grade it at all. The isolation
#   that separate mode buys is bought differently there — the verifier wipes
#   the database before grading and never reads /solution, both enforced by
#   check-verifier-contract.py.
set -u
TASK="${1:?usage: check-separate-verifier.sh <task-dir>}"

# Locate the repo root so we can call the common check by its real path.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$DIR"
while [ "$ROOT" != "/" ] && [ ! -f "$ROOT/core/registry.py" ]; do
  ROOT="$(dirname "$ROOT")"
done
COMMON="$ROOT/checks/check-separate-verifier.sh"

if compgen -G "$TASK/tests/*/judge.toml" >/dev/null 2>&1; then
  if [ -f "$COMMON" ]; then
    echo "NOTE $TASK: dimensions-shaped task — deferring to the common separate-verifier check."
    exec bash "$COMMON" "$TASK"
  fi
  echo "NOTE $TASK: common check-separate-verifier.sh not found at $COMMON; skipping."
  exit 0
fi

echo "NOTE $TASK: browser-rubric shape grades in the shared agent container by design; see check-verifier-contract.py."
exit 0
