#!/usr/bin/env bash
# OVERRIDE of the repo-root common check-task-fields.sh.
#
# The common check requires the terminal-bench metadata vocabulary
# (author_name, author_email, solution_explanation, verification_explanation,
# subcategory, tags, expert_time_estimate_hours, relevant_experience) and a
# category drawn from the seven terminal-bench domains. Neither task shape here
# uses it: the current format carries [metadata] difficulty/category/tags plus
# provenance and arena_slice, and the earlier one uses [task].authors with
# difficulty_explanation and task_id.
#
# The per-shape field contract is enforced by check-task-toml.py instead.
set -u
TASK="${1:?usage: check-task-fields.sh <task-dir>}"
echo "NOTE $TASK: terminal-bench task-fields vocabulary not used here; see check-task-toml.py."
exit 0
