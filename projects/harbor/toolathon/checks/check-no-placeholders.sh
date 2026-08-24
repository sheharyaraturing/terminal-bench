#!/usr/bin/env bash
# No unfinished TEMPLATE placeholders anywhere in the task.
set -u
TASK="${1:?usage: check-no-placeholders.sh <task-dir>}"
[ -d "$TASK" ] || { echo "FATAL: $TASK is not a directory"; exit 2; }
FAILED=0
while IFS= read -r -d '' f; do
  while IFS= read -r line; do
    echo "FAIL $line: unfinished TEMPLATE placeholder 'CHANGE-ME'"
    FAILED=1
  done < <(grep -nI "CHANGE-ME" "$f" | sed "s|^|$f:|")
done < <(find "$TASK" -type f ! -name "*.bundle" ! -name "*.db" ! -name "*.sqlite" ! -name "*.xlsx" -print0)
if [ "$FAILED" -eq 1 ]; then
  echo "check-no-placeholders: problem(s) found"
  exit 1
fi
echo "check-no-placeholders: OK ($TASK)"
