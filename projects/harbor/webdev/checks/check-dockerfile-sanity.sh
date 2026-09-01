#!/usr/bin/env bash
# OVERRIDE of the repo-root common check-dockerfile-sanity.sh.
#
# The common check hard-FAILS any Dockerfile that pins apt packages
# (`pkg=version`). The two task shapes disagree on this: the browser-rubric
# tasks pin every apt package deliberately, because their image is also the
# grading runtime; the current format does not pin. Neither answer is wrong
# enough to fail a task over, and the common check would fail one shape
# outright.
#
# check-dockerfiles.py takes the middle position for both shapes: unpinned apt
# is a NOTE explaining the reproducibility cost, while the pins that genuinely
# decide what the verifier runs — pip (==) and npm (@version) — stay hard
# failures. It also keeps the apt-update / apt-lists-cleanup hygiene the common
# check only warns about.
set -u
TASK="${1:?usage: check-dockerfile-sanity.sh <task-dir>}"
echo "NOTE $TASK: the apt-pin rule differs by task shape; see check-dockerfiles.py."
exit 0
