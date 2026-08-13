#!/usr/bin/env bash
# Oracle wrapper: locate Python, locate solve.py, run it, return its exit code.
# Fallback search paths live only here (never in solve.py or the tests).

mkdir -p /logs/agent /logs/verifier /logs/artifacts

echo "=== solve.sh starting ===" >&2
echo "cwd: $(pwd)" >&2

PY=""
for cand in /opt/venv/bin/python3 /usr/local/bin/python3 /usr/bin/python3 python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    PY="$cand"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "FATAL: no python interpreter found" >&2
  exit 127
fi

SOLVE=""
for cand in \
    /solution/solve.py \
    /root/solution/solve.py \
    /app/solution/solve.py \
    "$(dirname "$0")/solve.py"; do
  if [ -r "$cand" ]; then
    SOLVE="$cand"
    break
  fi
done
if [ -z "$SOLVE" ]; then
  echo "FATAL: solve.py not found" >&2
  exit 2
fi

echo "Using interpreter: $PY ($($PY --version 2>&1))" >&2
echo "Running: $PY $SOLVE" >&2

"$PY" "$SOLVE"
status=$?

echo "=== solve.sh done (status=$status) ===" >&2
exit "$status"
