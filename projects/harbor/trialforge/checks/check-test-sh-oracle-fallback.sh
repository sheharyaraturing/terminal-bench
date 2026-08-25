#!/usr/bin/env bash
# The oracle must produce the graded final answer.
#
# The judge reads final_answer.txt. For the oracle gate (`-a oracle`) to pass,
# that file must exist for an oracle run. There are two valid mechanisms in this
# suite, and EITHER satisfies the contract:
#
#   1. solution/solve.sh writes/tees the answer to final_answer.txt itself
#      (the pattern every task in this suite uses under environment_mode="separate",
#      where the verifier sees /logs/artifacts and never /logs/agent). This is the
#      custom harness: solve.sh publishes the answer, so no bridge is needed.
#   2. tests/test.sh bridges Harbor's OracleAgent stdout (/logs/agent/oracle.txt)
#      into final_answer.txt for tasks that rely on the default OracleAgent.
#
# Only when NEITHER mechanism is present can the oracle gate never pass.
set -u

TASK="${1:?usage: check-test-sh-oracle-fallback.sh <task-dir>}"
[ -d "$TASK" ] || { echo "FATAL: $TASK is not a directory"; exit 2; }

REWARD="$TASK/tests/reward.toml"
TEST_SH="$TASK/tests/test.sh"
SOLVE="$TASK/solution/solve.sh"

# Only relevant when the judge reads final_answer.txt.
if [ -f "$REWARD" ] && grep -q "final_answer\.txt" "$REWARD"; then
  # Mechanism 1: the oracle writes the graded file itself.
  if [ -f "$SOLVE" ] && grep -q "final_answer\.txt" "$SOLVE"; then
    echo "check-test-sh-oracle-fallback: OK ($TASK) — solve.sh publishes final_answer.txt directly"
    exit 0
  fi
  # Mechanism 2: test.sh bridges the default OracleAgent output.
  if [ -f "$TEST_SH" ] && grep -q "oracle\.txt" "$TEST_SH"; then
    echo "check-test-sh-oracle-fallback: OK ($TASK) — test.sh bridges oracle.txt"
    exit 0
  fi
  echo "FAIL $TASK: nothing publishes the oracle answer to final_answer.txt."
  echo "  The judge reads final_answer.txt, but neither solution/solve.sh writes it"
  echo "  (e.g. tee /logs/artifacts/final_answer.txt) nor does tests/test.sh bridge"
  echo "  Harbor's OracleAgent output (/logs/agent/oracle.txt) into it. Without one of"
  echo "  these the \`-a oracle\` gate can never pass."
  echo "check-test-sh-oracle-fallback: problem(s) found"
  exit 1
fi
echo "check-test-sh-oracle-fallback: OK ($TASK)"
