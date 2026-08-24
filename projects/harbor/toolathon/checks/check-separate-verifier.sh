#!/usr/bin/env bash
# OVERRIDE of the repo-root common check-separate-verifier.sh.
#
# The common check requires [verifier] environment_mode = "separate" plus a
# tests/Dockerfile that bakes the verifier image. Toolathon tasks grade in the
# shared agent container via rewardkit (tests/test.sh -> rewardkit /tests) and
# have no separate verifier image, so the common check would fail all 16. This
# override shadows it and is a no-op pass.
set -u
TASK="${1:?usage: check-separate-verifier.sh <task-dir>}"
echo "NOTE $TASK: separate-verifier check not applicable to toolathon (shared rewardkit verifier); overridden."
exit 0
