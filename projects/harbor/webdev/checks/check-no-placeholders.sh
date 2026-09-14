#!/usr/bin/env bash
# No unfinished template markers anywhere in the task.
#
# A task still carrying scaffolding parses, builds, and grades — it just grades
# the wrong thing, quietly. TODO/FIXME/XXX are included because a draft note
# left in a judge prompt or a criterion description is graded as if it were the
# rubric.
set -u
TASK="${1:?usage: check-no-placeholders.sh <task-dir>}"
[ -d "$TASK" ] || { echo "FATAL: $TASK is not a directory"; exit 2; }

FAILED=0
while IFS= read -r -d '' f; do
  while IFS= read -r line; do
    echo "FAIL $f:$line"
    FAILED=1
  done < <(grep -nIE 'CHANGE-ME|\{\{(name|description|validation_mode|slug)\}\}|\b(TODO|FIXME|XXX|TBD)\b|<[a-z_]*placeholder[a-z_]*>|[Ll]orem ipsum' "$f" 2>/dev/null)
done < <(find "$TASK" -type f \
           ! -path '*/node_modules/*' ! -path '*/.git/*' \
           ! -name 'package-lock.json' \
           ! -name '*.db' ! -name '*.sqlite' ! -name '*.sqlite3' \
           ! -name '*.zip' ! -name '*.xlsx' ! -name '*.docx' \
           ! -name '*.png' ! -name '*.jpg' ! -name '*.jpeg' ! -name '*.gif' \
           ! -name '*.woff' ! -name '*.woff2' ! -name '*.ttf' \
           ! -name '*.mp3' ! -name '*.mp4' ! -name '*.wasm' \
           -print0)

if [ "$FAILED" -eq 1 ]; then
  echo "check-no-placeholders: unfinished template marker(s) found"
  exit 1
fi
echo "check-no-placeholders: OK ($TASK)"
