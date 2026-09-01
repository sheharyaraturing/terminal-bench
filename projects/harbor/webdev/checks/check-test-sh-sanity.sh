#!/usr/bin/env bash
# OVERRIDE of the repo-root common check-test-sh-sanity.sh.
#
# The common check requires a SHARED-mode tests/test.sh to isolate its tooling
# behind uv / npm / npx / pnpm, on the reasoning that the verifier would
# otherwise install into the agent's container at trial time. It already skips
# separate-mode tasks, so the current format is unaffected either way.
#
# For the browser-rubric shape the premise does not hold: that test.sh installs
# nothing. It is a ~20-line wrapper that runs `python3 test.py` with the
# interpreter, harbor-rewardkit, claude-code, and Playwright already baked into
# environment/Dockerfile at build time. That is a stronger property than the
# isolation the common check asks for, not a weaker one.
#
# check-verifier-contract.py enforces what actually matters about test.sh (a
# reward on every exit path, no `exec`, no `set -e` without a trap), and
# check-dockerfiles.py enforces that the toolchain is baked.
set -u
TASK="${1:?usage: check-test-sh-sanity.sh <task-dir>}"

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$DIR"
while [ "$ROOT" != "/" ] && [ ! -f "$ROOT/core/registry.py" ]; do
  ROOT="$(dirname "$ROOT")"
done
COMMON="$ROOT/checks/check-test-sh-sanity.sh"

if compgen -G "$TASK/tests/*/judge.toml" >/dev/null 2>&1 && [ -f "$COMMON" ]; then
  echo "NOTE $TASK: dimensions-shaped task — deferring to the common test-sh-sanity check."
  exec bash "$COMMON" "$TASK"
fi

echo "NOTE $TASK: uv/npm isolation not applicable to the browser-rubric shape (test.sh installs nothing; the toolchain is baked into the image); see check-verifier-contract.py."
exit 0
