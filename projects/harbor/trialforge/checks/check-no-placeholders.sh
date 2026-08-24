#!/usr/bin/env bash
# No unfinished TEMPLATE placeholders anywhere in the task.
#
# A task that still contains the scaffolding markers was copied from TEMPLATE
# and not finished. The judge would happily grade
# "CHANGE-ME: states that <specific fact> is <specific value>".
set -u

TASK="${1:?usage: check-no-placeholders.sh <task-dir>}"
[ -d "$TASK" ] || { echo "FATAL: $TASK is not a directory"; exit 2; }

FAILED=0
# Skip binary fixtures; grep -I already skips binaries, but exclude bundles/dbs
# by name so a binary blob with the bytes CHANGE-ME in it cannot false-fire.
while IFS= read -r -d '' f; do
  # -n: line numbers; -I: skip binary
  while IFS= read -r line; do
    echo "FAIL $line: unfinished TEMPLATE placeholder 'CHANGE-ME'"
    FAILED=1
  done < <(grep -nI "CHANGE-ME" "$f" | sed "s|^|$f:|")
done < <(find "$TASK" -type f ! -name "*.bundle" ! -name "*.db" ! -name "*.sqlite" -print0)

if [ "$FAILED" -eq 1 ]; then
  echo "check-no-placeholders: problem(s) found"
  exit 1
fi
echo "check-no-placeholders: OK ($TASK)"
