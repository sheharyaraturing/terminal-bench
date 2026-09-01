#!/usr/bin/env bash
# OVERRIDE of the repo-root common check-instruction-suffix.sh.
#
# The common check requires instruction.md to end with the canonical
# "You have N seconds to complete this task. Do not cheat..." line. A webdev
# instruction.md is a shop-floor brief written as field notes; appending a
# harness-flavoured sentence to it would break the framing the task's whole
# difficulty rests on (the agent must infer invariants from complaints, not
# read a checklist). Neither shipped task carries the suffix.
#
# Brief quality is covered by check-instruction-hygiene.py instead.
set -u
TASK="${1:?usage: check-instruction-suffix.sh <task-dir>}"
echo "NOTE $TASK: instruction-suffix check not applicable to webdev (the brief is deliberately in-world prose); see check-instruction-hygiene.py."
exit 0
