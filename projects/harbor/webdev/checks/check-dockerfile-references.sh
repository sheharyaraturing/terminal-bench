#!/usr/bin/env bash
# OVERRIDE of the repo-root common check-dockerfile-references.sh — a FIX, not
# a waiver.
#
# The common check greps for the literal strings "solution/solve.sh",
# "tests/test.sh", and "tests/test_*.py". The third is passed to grep as a basic
# regex, where `_*` means "zero or more underscores" and `.` matches any
# character — so it matches the plain text "tests/test.py". Both webdev
# Dockerfiles mention tests/test.py in a comment explaining how the verifier
# starts the app, and are failed for it.
#
# This override keeps the real rule (the image must not carry the solution or
# the grading code) and applies it to actual COPY/ADD instructions, where the
# leak would happen, instead of to any substring anywhere in the file.
set -u
TASK="${1:?usage: check-dockerfile-references.sh <task-dir>}"
DOCKERFILE="$TASK/environment/Dockerfile"
[ -f "$DOCKERFILE" ] || { echo "check-dockerfile-references: no $DOCKERFILE, skipping"; exit 0; }

FAILED=0
# Join backslash continuations, drop comment lines, keep COPY/ADD only.
while IFS= read -r line; do
  case "$line" in
    [Cc][Oo][Pp][Yy]*|[Aa][Dd][Dd]*) ;;
    *) continue ;;
  esac
  if echo "$line" | grep -qE '(^|[[:space:]/])(solution|solve\.sh|tests?|test\.(sh|py)|rubric|browser\.toml|segments\.json)([[:space:]/]|$)'; then
    echo "FAIL $DOCKERFILE: COPY/ADD references solution or grading code: $line"
    echo "  The image build context is environment/. The golden solution and the"
    echo "  rubric must never reach the agent's container."
    FAILED=1
  fi
done < <(sed -e ':a' -e '/\\$/{N;s/\\\n//;ba' -e '}' "$DOCKERFILE" | grep -v '^[[:space:]]*#' | sed 's/^[[:space:]]*//')

if [ "$FAILED" -eq 1 ]; then
  exit 1
fi
echo "check-dockerfile-references: OK ($TASK)"
