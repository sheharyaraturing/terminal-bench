#!/usr/bin/env bash
# OVERRIDE of the repo-root common check-task-package-name.sh.
#
# The common check requires [task].name = "terminal-bench/<folder>". Toolathon
# publishes under the "context-mesh" org (name = "context-mesh/<folder>"), so the
# common check would fail all 16. This override shadows it and is a no-op pass.
# The context-mesh naming contract is enforced by check-task-name.py instead.
set -u
TASK="${1:?usage: check-task-package-name.sh <task-dir>}"
echo "NOTE $TASK: terminal-bench package-name check not applicable to toolathon (context-mesh/*); see check-task-name.py."
exit 0
