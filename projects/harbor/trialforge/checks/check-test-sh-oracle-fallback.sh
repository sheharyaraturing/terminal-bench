#!/usr/bin/env bash
# The oracle trap: test.sh must reconcile oracle.txt with final_answer.txt.
#
# Harbor's OracleAgent writes solve.sh stdout to /logs/agent/oracle.txt. The
# wrapper writes /logs/agent/final_answer.txt. If the judge only reads
# final_answer.txt, the oracle produces no evidence and the oracle gate can
# NEVER pass - a permanently red pipeline that looks like a bad task.
set -u

TASK="${1:?usage: check-test-sh-oracle-fallback.sh <task-dir>}"
[ -d "$TASK" ] || { echo "FATAL: $TASK is not a directory"; exit 2; }

REWARD="$TASK/tests/reward.toml"
TEST_SH="$TASK/tests/test.sh"

# Only applies when the judge reads final_answer.txt.
if [ -f "$REWARD" ] && grep -q "final_answer\.txt" "$REWARD"; then
  if [ ! -f "$TEST_SH" ] || ! grep -q "oracle\.txt" "$TEST_SH"; then
    echo "FAIL $TEST_SH: [judge].files reads final_answer.txt, but Harbor's oracle writes"
    echo "  its stdout to /logs/agent/oracle.txt and never creates final_answer.txt."
    echo "  test.sh must fall back, e.g.:"
    echo "    [ -s /logs/agent/final_answer.txt ] || cp /logs/agent/oracle.txt /logs/agent/final_answer.txt 2>/dev/null || true"
    echo "  Without it the \`-a oracle\` gate can never pass."
    echo "check-test-sh-oracle-fallback: problem(s) found"
    exit 1
  fi
fi
echo "check-test-sh-oracle-fallback: OK ($TASK)"
