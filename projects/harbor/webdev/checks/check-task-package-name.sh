#!/usr/bin/env bash
# OVERRIDE of the repo-root common check-task-package-name.sh.
#
# The common check requires [task].name = "terminal-bench/<folder>". This
# project publishes under "codearena" (the current format) or "webdev" (the
# earlier browser-rubric tasks).
#
# The naming contract is enforced by check-task-name.py instead, which also
# checks the last path component against the directory name.
set -u
TASK="${1:?usage: check-task-package-name.sh <task-dir>}"
echo "NOTE $TASK: terminal-bench package-name check not applicable here (codearena/* or webdev/*); see check-task-name.py."
exit 0
