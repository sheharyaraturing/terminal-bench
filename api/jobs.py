"""Background executor: runs the three-leg pipeline off the request thread.

Reuses core.deterministic / core.rubric / core.validation / core.report
verbatim, so an API run and a `python execute.py` run produce the same report.
"""
from __future__ import annotations

import os
import traceback
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.deterministic import run_deterministic
from core.progress import RunCancelled, RunControl
from core.registry import REPO_ROOT, load_project, resolve_task
from core.report import compile_report
from core.rubric import run_rubric
from core.validation import run_validation

from . import store

# Reviews are long and mostly wait on Docker or the Anthropic API, so a small
# pool is plenty; it also keeps concurrent Docker builds from thrashing.
MAX_WORKERS = int(os.environ.get("AUTOREVIEWER_MAX_WORKERS", "2"))
REPORTS_DIR = REPO_ROOT / "reports"

_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="review")

# Live controls for runs that are queued or in flight, so they can be stopped.
_controls: dict[str, RunControl] = {}
_controls_lock = threading.Lock()


def cancel_run(run_id: str) -> bool:
    """Stop a queued or running review. False if it is not active."""
    with _controls_lock:
        control = _controls.get(run_id)
    if control is None:
        return False
    control.cancel()
    return True


def is_active(run_id: str) -> bool:
    with _controls_lock:
        return run_id in _controls


def submit_run(
    project_name: str,
    task_id: str,
    project_id: str | None = None,
    reviewer_email: str | None = None,
) -> dict:
    """Validate inputs, create the run record, and queue it. Raises on bad input."""
    project = load_project(project_name)  # FileNotFoundError if unknown
    resolve_task(project, task_id)  # FileNotFoundError if unknown

    status = store.create_run(
        project=project.name,
        task_id=task_id,
        project_type=project.type,
        project_id=project_id,
        reviewer_email=reviewer_email,
    )
    run_id = status["run_id"]
    with _controls_lock:
        _controls[run_id] = RunControl(
            on_progress=lambda msg, rid=run_id: store.append_log(rid, msg)
        )
    _executor.submit(_execute, run_id, project.name, task_id)
    return status


def _execute(run_id: str, project_name: str, task_id: str) -> None:
    log = lambda msg: store.append_log(run_id, msg)
    with _controls_lock:
        control = _controls.get(run_id)
    if control is None or control.cancelled.is_set():
        _finish_cancelled(run_id, log)
        return
    try:
        store.update_status(run_id, state="running", started_at=store.now_iso())
        project = load_project(project_name)
        task_path = resolve_task(project, task_id)
        log(f"project: {project.name} ({project.type})")
        log(f"task:    {task_id} -> {task_path}")

        # Harbor job trees (check / oracle / nop) land here so
        # `harbor view --jobs runs/<run_id>/harbor` works after the run.
        harbor_dir = store.run_dir(run_id) / "harbor"
        harbor_dir.mkdir(parents=True, exist_ok=True)
        store.update_status(run_id, harbor_jobs=str(harbor_dir))

        # --- 1/3 deterministic ---
        store.set_leg(run_id, "deterministic", "running")
        log("[1/3] deterministic checks")
        det = run_deterministic(project, task_path, control)
        for c in det.checks:
            log(f"  {'PASS' if c.passed else 'FAIL'}  [{c.source}] {c.name}")
        if not det.checks:
            log("  (no checks configured)")
        passed_n = sum(1 for c in det.checks if c.passed)
        store.set_leg(
            run_id,
            "deterministic",
            "passed" if det.passed else "failed",
            f"{passed_n}/{len(det.checks)} passed",
        )

        # --- 2/3 rubric ---
        store.set_leg(run_id, "rubric", "running")
        log("[2/3] LLM rubric review")
        rub = run_rubric(project, task_path, control, jobs_dir=harbor_dir)
        if rub.skipped:
            log(f"  skipped: {rub.skip_reason}")
            store.set_leg(run_id, "rubric", "skipped", rub.skip_reason)
        else:
            for v in rub.verdicts:
                log(f"  {v.verdict.upper()}  {v.name}: {v.reason}")
            ok_n = sum(1 for v in rub.verdicts if v.verdict in ("pass", "not_applicable"))
            store.set_leg(
                run_id,
                "rubric",
                "passed" if rub.passed else "failed",
                f"{ok_n}/{len(rub.verdicts)} criteria ok",
            )

        # --- 3/3 validation ---
        store.set_leg(run_id, "validation", "running")
        log("[3/3] validation")
        val = run_validation(project, task_path, control, jobs_dir=harbor_dir)
        if val.skipped:
            log(f"  skipped: {val.skip_reason}")
            store.set_leg(run_id, "validation", "skipped", val.skip_reason)
        else:
            log(f"  oracle={val.oracle_reward} nop={val.nop_reward} {val.details}")
            store.set_leg(
                run_id, "validation", "passed" if val.passed else "failed", val.details
            )

        log(f"harbor jobs: {harbor_dir}")
        log(f"view with: harbor view --jobs {harbor_dir}")

        report = compile_report(project.name, task_id, det, rub, val)
        store.write_report(run_id, report.to_json() + "\n")

        # Mirror to reports/ so CLI and API output land in the same place.
        REPORTS_DIR.mkdir(exist_ok=True)
        mirror = REPORTS_DIR / f"{task_id}_{run_id[:8]}.json"
        report.write(mirror)
        log(f"report written to {mirror}")

        log(f"overall: {'PASS' if report.passed else 'FAIL'}")
        store.update_status(
            run_id,
            state="passed" if report.passed else "failed",
            passed=report.passed,
            finished_at=store.now_iso(),
        )
    except RunCancelled:
        _finish_cancelled(run_id, log)
    except Exception as exc:
        store.append_log(run_id, f"ERROR: {exc}")
        store.append_log(run_id, traceback.format_exc())
        store.update_status(
            run_id,
            state="error",
            passed=False,
            error=str(exc),
            finished_at=store.now_iso(),
        )
    finally:
        with _controls_lock:
            _controls.pop(run_id, None)


def _finish_cancelled(run_id: str, log) -> None:
    log("run cancelled")
    status = store.read_status(run_id)
    for leg, detail in status.get("legs", {}).items():
        if detail.get("state") in ("running", "pending"):
            store.set_leg(run_id, leg, "cancelled", detail.get("summary", ""))
    store.update_status(
        run_id,
        state="cancelled",
        passed=False,
        error="cancelled by user",
        finished_at=store.now_iso(),
    )
