#!/usr/bin/env bash
# OVERRIDE of the repo-root common check-task-timeout.sh.
#
# The common check caps BOTH [agent].timeout_sec and [verifier].timeout_sec at
# 18000s (5h). The agent cap is right and is kept — enforced by
# check-timeout-hierarchy.py. The verifier cap is not applicable: a webdev
# verifier is a chain of CUA judge invocations (33 of them in the segmented
# task), and its timeout_sec is a worst-case budget in which every segment
# times out, not an expected runtime. Capping it at 5h would mean a single slow
# segment SIGKILLs the verifier onto the 0.0 placeholder and discards the
# criteria already earned.
#
# check-timeout-hierarchy.py enforces the agent cap, the strict
# judge < rewardkit < verifier ordering, and a soft ceiling NOTE on the
# verifier budget.
set -u
TASK="${1:?usage: check-task-timeout.sh <task-dir>}"
echo "NOTE $TASK: split-cap timeout check not applicable to webdev as written (the verifier budget is a worst-case segment chain); see check-timeout-hierarchy.py."
exit 0
