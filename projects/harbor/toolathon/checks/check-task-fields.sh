#!/usr/bin/env bash
# OVERRIDE of the repo-root common check-task-fields.sh.
#
# The common check requires terminal-bench metadata fields (author_name,
# author_email, difficulty_explanation, subcategory, tags, ...). Toolathon
# task.toml carries only [metadata] difficulty + category, so the common check
# would fail all 16. This override shadows it and is a no-op pass. The toolathon
# field contract is enforced by check-task-toml.py instead.
set -u
TASK="${1:?usage: check-task-fields.sh <task-dir>}"
echo "NOTE $TASK: terminal-bench task-fields check not applicable to toolathon (difficulty+category only); see check-task-toml.py."
exit 0
