#!/usr/bin/env bash
# Verifier entrypoint: run the pytest suite and emit the reward file.
# pytest and pytest-json-ctrf are installed by environment/Dockerfile.

mkdir -p /logs/agent /logs/verifier /logs/artifacts

PY=""
for cand in /opt/venv/bin/python3 /usr/local/bin/python3 /usr/bin/python3 python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done

if [ -z "$PY" ]; then
  echo "FATAL: no python interpreter found"
  echo 0 > /logs/verifier/reward.txt
  exit 0
fi

"$PY" -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA -v
status=$?

if [ "$status" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi

exit 0
