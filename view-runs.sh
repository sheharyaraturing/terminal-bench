#!/usr/bin/env bash
# View every Harbor job stored under runs/*/harbor/ in one Harbor Viewer.
#
# Usage (from repo root):
#   ./view-runs.sh
#   ./view-runs.sh -p 8082
#   ./view-runs.sh /path/to/runs
#
# Harbor's viewer expects a folder whose *children* are job directories
# (timestamped check jobs, oracle/, nop/, …). Our Autoreviewer keeps those
# under runs/<run_id>/harbor/, so this script builds a flat symlink farm and
# points `harbor view --jobs` at it.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
RUNS_DIR="${ROOT}/runs"
PORT_ARGS=()

# Optional: first non-flag arg is an alternate runs/ directory.
while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--port)
      PORT_ARGS+=(-p "$2")
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
View every Harbor job stored under runs/*/harbor/ in one Harbor Viewer.

Usage (from repo root):
  ./view-runs.sh
  ./view-runs.sh -p 8082
  ./view-runs.sh /path/to/runs
EOF
      exit 0
      ;;
    -*)
      echo "unknown option: $1" >&2
      exit 2
      ;;
    *)
      RUNS_DIR="$(cd "$1" && pwd)"
      shift
      ;;
  esac
done

if [[ ! -d "$RUNS_DIR" ]]; then
  echo "no runs directory at ${RUNS_DIR}" >&2
  exit 1
fi

if ! command -v harbor >/dev/null 2>&1; then
  echo "harbor is not on PATH" >&2
  exit 1
fi

# Fresh merge dir each time so deleted runs disappear and names stay unique.
MERGE="$(mktemp -d "${TMPDIR:-/tmp}/harbor-runs-view.XXXXXX")"
trap 'rm -rf "$MERGE"' EXIT

linked=0
# A Harbor job dir has result.json or config.json at its root.
is_job_dir() {
  local d="$1"
  [[ -f "${d}/result.json" || -f "${d}/config.json" || -f "${d}/job.log" ]]
}

shopt -s nullglob
for harbor in "${RUNS_DIR}"/*/harbor; do
  [[ -d "$harbor" ]] || continue
  run_id="$(basename "$(dirname "$harbor")")"
  for job in "${harbor}"/*; do
    [[ -d "$job" ]] || continue
    if ! is_job_dir "$job"; then
      continue
    fi
    name="$(basename "$job")"
    # Prefix with a short run id so two runs' "oracle" jobs don't collide.
    dest="${MERGE}/${run_id:0:8}__${name}"
    # Copy (not symlink): harbor view rejects paths that resolve outside the
    # folder it was given, so symlinks into runs/…/harbor/… fail its
    # path-traversal check with HTTP 400 on every file-read endpoint
    # (trajectory, agent-logs, files/…). -L dereferences any symlinks
    # inside the job tree too (agent/sessions/…).
    cp -RL "$job" "$dest"
    linked=$((linked + 1))
  done
done
shopt -u nullglob

if [[ "$linked" -eq 0 ]]; then
  echo "no Harbor jobs found under ${RUNS_DIR}/*/harbor/" >&2
  echo "re-run a review first (API or execute.py) so jobs are persisted." >&2
  exit 1
fi

echo "linked ${linked} job(s) from ${RUNS_DIR} into ${MERGE}"
echo "starting Harbor Viewer…"
# Don't exec: keep the EXIT trap so the symlink farm is cleaned up on Ctrl+C.
harbor view --jobs "${PORT_ARGS[@]}" "$MERGE"
