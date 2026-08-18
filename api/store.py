"""Filesystem-backed run store.

Each run owns a directory under runs/<run_id>/:

    status.json   run metadata, state, per-leg progress
    log.txt       append-only human-readable log the UI tails
    report.json   the compiled EvaluationReport, once the run finishes

Keeping this on disk (rather than in memory) means runs survive a server
restart and can be inspected by hand while they are still going.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.registry import REPO_ROOT

RUNS_ROOT = REPO_ROOT / "runs"

# Terminal states; anything else means the run is still in flight.
TERMINAL_STATES = ("passed", "failed", "error")

_RUN_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# Guards read-modify-write of status.json; runs execute on worker threads.
_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or not _RUN_ID_RE.match(run_id):
        raise ValueError(f"invalid run id: {run_id!r}")
    return run_id


def run_dir(run_id: str) -> Path:
    return RUNS_ROOT / validate_run_id(run_id)


def create_run(
    project: str,
    task_id: str,
    project_type: str = "",
    project_id: str | None = None,
    reviewer_email: str | None = None,
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    status = {
        "run_id": run_id,
        "project": project,
        "project_id": project_id,
        "project_type": project_type,
        "task_id": task_id,
        "reviewer_email": reviewer_email,
        "state": "queued",
        "passed": None,
        "error": None,
        "legs": {
            "deterministic": {"state": "pending", "summary": ""},
            "rubric": {"state": "pending", "summary": ""},
            "validation": {"state": "pending", "summary": ""},
        },
        "created_at": now_iso(),
        "started_at": None,
        "finished_at": None,
    }
    d = run_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "log.txt").touch()
    _write_status(run_id, status)
    return status


def _write_status(run_id: str, status: dict[str, Any]) -> None:
    path = run_dir(run_id) / "status.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(status, indent=2) + "\n")
    tmp.replace(path)  # atomic, so a polling reader never sees a half-written file


def read_status(run_id: str) -> dict[str, Any]:
    path = run_dir(run_id) / "status.json"
    if not path.is_file():
        raise FileNotFoundError(f"run not found: {run_id}")
    return json.loads(path.read_text())


def update_status(run_id: str, **fields: Any) -> dict[str, Any]:
    with _lock:
        status = read_status(run_id)
        status.update(fields)
        _write_status(run_id, status)
        return status


def set_leg(run_id: str, leg: str, state: str, summary: str = "") -> None:
    with _lock:
        status = read_status(run_id)
        status["legs"][leg] = {"state": state, "summary": summary}
        _write_status(run_id, status)


def append_log(run_id: str, message: str) -> None:
    line = f"[{now_iso()}] {message}\n"
    with (run_dir(run_id) / "log.txt").open("a") as f:
        f.write(line)


def read_log(run_id: str, offset: int = 0) -> tuple[str, int]:
    """Return (text_since_offset, new_offset) for incremental polling."""
    path = run_dir(run_id) / "log.txt"
    if not path.is_file():
        return "", offset
    data = path.read_bytes()
    if offset > len(data):  # log was truncated/recreated; restart from the top
        offset = 0
    chunk = data[offset:]
    return chunk.decode(errors="replace"), len(data)


def write_report(run_id: str, report_json: str) -> Path:
    path = run_dir(run_id) / "report.json"
    path.write_text(report_json)
    return path


def read_report(run_id: str) -> dict[str, Any]:
    path = run_dir(run_id) / "report.json"
    if not path.is_file():
        raise FileNotFoundError(f"no report for run: {run_id}")
    return json.loads(path.read_text())


def list_runs(limit: int = 50, project: str | None = None) -> list[dict[str, Any]]:
    """Newest-first run summaries."""
    if not RUNS_ROOT.is_dir():
        return []
    runs: list[dict[str, Any]] = []
    for d in RUNS_ROOT.iterdir():
        if not d.is_dir() or not (d / "status.json").is_file():
            continue
        try:
            status = json.loads((d / "status.json").read_text())
        except Exception:
            continue
        if project and status.get("project") != project:
            continue
        runs.append(status)
    runs.sort(key=lambda s: s.get("created_at") or "", reverse=True)
    return runs[:limit]
