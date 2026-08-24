#!/usr/bin/env bash
# tests/test.sh must actually produce a reward, and must not strand Harbor on failure.
#
# Two distinct failure modes this guards:
#
#   1. test.sh never invokes rewardkit. rewardkit is what discovers reward.toml,
#      calls the judge, and writes /logs/verifier/reward.json. Without it the
#      verifier produces nothing and Harbor reports RewardFileNotFoundError.
#
#   2. test.sh has no fallback reward write. Harbor requires a reward file on
#      EVERY code path; rewardkit skips writing when it crashes (missing API key,
#      judge error, etc.). A test.sh that only runs `python3 -m rewardkit` and
#      relies on `set -e` aborts with no reward file on any judge failure - the
#      trial then reads as an infrastructure error, not a scored 0.0.
#
# Mode 1 is a hard FAIL (no reward is ever produced). Mode 2 is a NOTE: the task
# still scores on the happy path, but a judge hiccup becomes an unhelpful error.
set -u

TASK="${1:?usage: check-test-sh-rewardkit.sh <task-dir>}"
TEST_SH="$TASK/tests/test.sh"
[ -f "$TEST_SH" ] || { echo "FAIL $TEST_SH: missing (check-required-files also enforces this)"; exit 1; }

FAILED=0

# 1. rewardkit must be invoked (module form or CLI).
if ! grep -qE '(python3?[[:space:]]+-m[[:space:]]+)?rewardkit' "$TEST_SH"; then
  echo "FAIL $TEST_SH: never invokes rewardkit. rewardkit discovers tests/reward.toml,"
  echo "  calls the judge, and writes /logs/verifier/reward.json - without it no reward"
  echo "  is produced and Harbor reports RewardFileNotFoundError."
  FAILED=1
fi

# 2. Fallback reward write (advisory). Look for a write of a zero reward to the
#    reward file, e.g. printf '%s\n' '{"reward": 0.0}' >"$REWARD_JSON".
if ! grep -qE '\{"reward":[[:space:]]*0(\.0)?\}' "$TEST_SH"; then
  echo "NOTE $TEST_SH: no fallback reward write found. Harbor requires a reward file on"
  echo "  every code path; if rewardkit crashes (missing OPENROUTER_API_KEY, judge error)"
  echo "  and nothing writes {\"reward\": 0.0}, the trial reads as RewardFileNotFoundError"
  echo "  instead of a scored 0.0. Consider a write_fallback_reward() trap."
fi

if [ "$FAILED" -eq 1 ]; then
  echo "check-test-sh-rewardkit: problem(s) found"
  exit 1
fi
echo "check-test-sh-rewardkit: OK ($TASK)"
