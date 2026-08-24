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
TERMINAL_STATES = ("passed", "failed", "error", "cancelled")

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
    kind: str = "review",
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    if kind == "trajectory":
        legs: dict[str, Any] = {"trajectory": {"state": "pending", "summary": ""}}
    else:
        legs = {
            "deterministic": {"state": "pending", "summary": ""},
            "rubric": {"state": "pending", "summary": ""},
            "validation": {"state": "pending", "summary": ""},
        }
    status = {
        "run_id": run_id,
        "project": project,
        "project_id": project_id,
        "project_type": project_type,
        "kind": kind,
        "task_id": task_id,
        "reviewer_email": reviewer_email,
        "state": "queued",
        "passed": None,
        "error": None,
        "legs": legs,
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


# ── project jobs (trajectories) ─────────────────────────────────────────────
# Uploaded trajectories zips are extracted into the project's own jobs/ dir
# (projects/<type>/<name>/jobs/) as a Harbor jobs tree, so the frontend can
# list existing folders/runs and rerun analysis on them directly.

def _ignored_seg(seg: str) -> bool:
    return seg in ("__MACOSX", ".DS_Store") or seg.startswith("._")


def project_jobs_dir(project) -> Path:
    return project.root / "jobs"


def inspect_jobs_tree(jobs_dir: Path) -> dict[str, Any]:
    """Walk a Harbor jobs directory and return its folder/run tree.

    Shape: {"folders": [{"name": <job dir>, "runs": [{"name": <trial dir>, "path": <rel>}]}]}.
    A "run" is a directory containing agent/trajectory.json. A top-level dir
    that is itself a trial dir surfaces as a single folder with one run.
    """
    folders: dict[str, list[dict[str, str]]] = {}
    if not jobs_dir.is_dir():
        return {"folders": []}
    for traj in sorted(jobs_dir.rglob("agent/trajectory.json")):
        trial_dir = traj.parent.parent  # .../<trial>/agent/trajectory.json
        rel = trial_dir.relative_to(jobs_dir).as_posix()
        segs = rel.split("/")
        folder = segs[0] if len(segs) > 1 else segs[0]
        run = segs[-1]
        folders.setdefault(folder, []).append({"name": run, "path": rel})
    return {
        "folders": [
            {"name": name, "runs": runs} for name, runs in sorted(folders.items())
        ]
    }


def list_project_jobs(project) -> dict[str, Any]:
    """The folder/run tree currently in the project's jobs dir (rerun view)."""
    return {"tree": inspect_jobs_tree(project_jobs_dir(project))}


def extract_trajectory_zip(project, zip_bytes: bytes) -> dict[str, Any]:
    """Extract a trajectories zip into the project's jobs dir and return the
    resulting tree plus the folder names that were added/merged."""
    import io
    import zipfile

    jobs_dir = project_jobs_dir(project)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    added: set[str] = set()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = [p for p in info.filename.replace("\\", "/").split("/") if p]
            if not parts or any(_ignored_seg(p) for p in parts):
                continue
            if any(p == ".." for p in parts):
                continue
            added.add(parts[0])
            target = jobs_dir.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as out:
                import shutil as _sh
                _sh.copyfileobj(src, out, length=1024 * 1024)
    return {"tree": inspect_jobs_tree(jobs_dir), "added": sorted(added)}
