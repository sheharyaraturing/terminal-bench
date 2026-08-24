#!/bin/bash
# Harbor's verifier entrypoint. Runs in a SEPARATE container that sees
# /logs/artifacts but not /logs/agent, so the answer must be published there.
set -euo pipefail

export OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}"

ART=/logs/artifacts
mkdir -p "$ART"

if [ ! -s "$ART/final_answer.txt" ]; then
  python3 - <<'PY' || true
import glob, json, pathlib

def last_agent_message(path):
    """Last agent-authored message. ATIF: {"steps":[{"source":"agent",...}]}."""
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

# Never leave the judge with no file: rewardkit raises before reward.json exists
# and harbor reports an opaque RewardFileNotFoundError.
[ -s "$ART/final_answer.txt" ] || echo "(no agent output captured)" > "$ART/final_answer.txt"

# uv comes from tests/Dockerfile; uvx pins rewardkit with no pip step.
uvx --from 'harbor-rewardkit==0.1.*' rewardkit /tests
