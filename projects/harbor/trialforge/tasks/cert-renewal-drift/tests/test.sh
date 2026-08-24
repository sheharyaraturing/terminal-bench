#!/bin/bash
# Harbor's verifier entrypoint. rewardkit discovers reward.toml in /tests and writes
# /logs/verifier/reward.json.
#
# This runs in a SEPARATE verifier container (see [verifier].environment_mode in
# task.toml), which can see /logs/artifacts and CANNOT see /logs/agent. Everything the
# judge reads must therefore have been published to /logs/artifacts during the trial:
#   - the parity agent writes it there itself (trialforge/agents/_harness_runner.py)
#   - solution/solve.sh tees it there for oracle runs
# The fallback below exists for any agent that publishes a trajectory but no answer file.
set -euo pipefail

export OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}"

ART=/logs/artifacts
mkdir -p "$ART"

if [ ! -s "$ART/final_answer.txt" ]; then
  python3 - <<'PY' || true
import glob, json, pathlib

def last_agent_message(path):
    """Last message authored by the agent. ATIF: {"steps":[{"source":"agent",...}]}."""
    try:
        doc = json.load(open(path, encoding="utf-8"))
    except Exception:
        return ""
    events = doc.get("steps") if isinstance(doc, dict) else doc
    if not isinstance(events, list):
        return ""
    best = ""
    for e in events:
        if not isinstance(e, dict) or e.get("source") != "agent":
            continue
        msg = e.get("message") or ""
        if e.get("action") == "finish" and msg:
            best = msg
        elif msg:
            best = msg
    return best

answer = ""
for p in sorted(glob.glob("/logs/artifacts/*trajectory*.json")):
    answer = last_agent_message(p) or answer
if answer.strip():
    pathlib.Path("/logs/artifacts/final_answer.txt").write_text(answer, encoding="utf-8")
PY
fi

# Never leave the judge with no file at all: an absent file raises inside rewardkit and
# `set -e` aborts before any reward.json exists, which harbor reports as
# RewardFileNotFoundError - an error that names a missing file and explains nothing.
[ -s "$ART/final_answer.txt" ] || echo "(no agent output captured)" > "$ART/final_answer.txt"

# uv comes from tests/Dockerfile; uvx pins the rewardkit version with no pip step.
uvx --from 'harbor-rewardkit==0.1.*' rewardkit /tests
