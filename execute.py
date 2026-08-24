#!/usr/bin/env python3
"""Multi-project autoreviewer PoC entry point.

Usage:
    python execute.py --project <name> --taskid <id> [--output report.json]

Examples:
    python execute.py --project skillbench --taskid 200068-team-roster-list-performance-and-storage-with-skill
    python execute.py --project servicenow --taskid task_20251126_055301_905_8e9e30d7_6aab00b8
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from core.deterministic import run_deterministic
from core.progress import RunControl
from core.registry import REPO_ROOT, list_projects, load_project, resolve_task
from core.report import compile_report, compile_trajectory_report
from core.rubric import run_rubric
from core.trajectory import run_trajectory_analysis
from core.validation import run_validation


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=VALUE lines, ignores comments and blanks."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the autoreviewer pipeline for a project task."
    )
    parser.add_argument("--project", required=False, help="Project name")
    parser.add_argument("--taskid", required=False, help="Task identifier")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Write JSON report to this path",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start the HTTP API and test UI instead of running a single task",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Poll Docker and print status of running review containers",
    )
    parser.add_argument(
        "--list-projects",
        action="store_true",
        help="List discovered projects and exit",
    )
    parser.add_argument(
        "--trajectories",
        type=Path,
        default=None,
        help="Run trajectory analysis only on a Harbor jobs .zip (or directory) "
        "instead of the three-leg review. --taskid is optional here. The "
        "project's own jobs/ dir (projects/<type>/<name>/jobs) is the intended "
        "source — pass it directly to analyze previously uploaded trajectories.",
    )
    parser.add_argument(
        "--selected",
        default=None,
        help="Comma-separated trial-directory paths (relative to the jobs tree) "
        "to analyze; omit to analyze every trial. Only used with --trajectories.",
    )
    return parser.parse_args(argv)


def _docker_available() -> bool:
    try:
        subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


def _print_status() -> None:
    """Print status of running harbor/review containers."""
    if not _docker_available():
        print("Docker is not available")
        return
    proc = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"],
        capture_output=True,
        text=True,
    )
    lines = [l for l in proc.stdout.splitlines() if "check-" in l or "rubric" in l or "harbor" in l]
    if not lines:
        print("No review containers running")
        return
    print("Running review containers:")
    for line in lines:
        name, status, image = line.split("\t")
        print(f"  {name}\t{status}\t{image}")
        # try to peek at claude-code log
        try:
            log = subprocess.run(
                ["docker", "exec", name, "tail", "-c", "500", "/logs/agent/claude-code.txt"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if log.returncode == 0 and log.stdout.strip():
                snippet = log.stdout.strip().splitlines()[-1][:120]
                print(f"    last: {snippet}")
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    _load_dotenv(Path(__file__).resolve().parent / ".env")
    args = parse_args(argv)

    if args.status:
        _print_status()
        return 0

    if args.serve:
        import uvicorn

        uvicorn.run(
            "api.main:app",
            host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", "8000")),
            reload=True,
        )
        return 0

    if args.list_projects:
        for p in list_projects():
            print(f"{p.name}\t{p.type}\t{p.root}")
        return 0

    if args.trajectories:
        return _run_trajectory(args)

    if not args.project or not args.taskid:
        print("error: --project and --taskid are required", file=sys.stderr)
        return 2

    try:
        project = load_project(args.project)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        task_path = resolve_task(project, args.taskid)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"project: {project.name} ({project.type})")
    print(f"task:    {args.taskid} -> {task_path}")

    # Live progress: every leg reports what it is doing as it happens.
    control = RunControl(on_progress=lambda msg: print(msg, flush=True))

    # Persist Harbor job trees under runs/<uuid>/harbor so
    # `harbor view --jobs …` works after the CLI run finishes.
    run_id = str(uuid.uuid4())
    harbor_dir = REPO_ROOT / "runs" / run_id / "harbor"
    harbor_dir.mkdir(parents=True, exist_ok=True)
    print(f"harbor:  {harbor_dir}")

    print("\n[1/3] deterministic checks")
    det = run_deterministic(project, task_path, control)
    for c in det.checks:
        status = "PASS" if c.passed else "FAIL"
        print(f"  {status}  [{c.source}] {c.name}")
    if not det.checks:
        print("  (no checks)")

    print("\n[2/3] LLM rubric review")
    try:
        rub = run_rubric(project, task_path, control, jobs_dir=harbor_dir)
    except KeyboardInterrupt:
        print("\ninterrupted — stopping the review and its containers...")
        control.cancel()
        return 130
    if rub.skipped:
        print(f"  skipped: {rub.skip_reason}")
    else:
        for v in rub.verdicts:
            print(f"  {v.verdict.upper()}  {v.name}: {v.reason}")

    print("\n[3/3] validation")
    val = run_validation(project, task_path, control, jobs_dir=harbor_dir)
    if val.skipped:
        print(f"  skipped: {val.skip_reason}")
    else:
        print(f"  oracle={val.oracle_reward} nop={val.nop_reward} {val.details}")

    report = compile_report(project.name, args.taskid, det, rub, val)

    # Always write to reports/<task_id>_<uuid>.json
    reports_dir = REPO_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    auto_path = reports_dir / f"{args.taskid}_{run_id[:8]}.json"
    report.write(auto_path)
    print(f"\nreport written to {auto_path}")

    # Also write to user-specified path if provided
    if args.output:
        report.write(args.output)
        print(f"report also written to {args.output}")

    print(f"\nharbor jobs: {harbor_dir}")
    print(f"view with:  harbor view --jobs {harbor_dir}")
    print(f"\noverall: {'PASS' if report.passed else 'FAIL'}")
    return 0 if report.passed else 1


def _run_trajectory(args: argparse.Namespace) -> int:
    if not args.project:
        print("error: --project is required for trajectory analysis", file=sys.stderr)
        return 2
    try:
        project = load_project(args.project)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    task_path = None
    if args.taskid:
        try:
            task_path = resolve_task(project, args.taskid)
        except FileNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if not args.trajectories.exists():
        print(f"error: trajectories path not found: {args.trajectories}", file=sys.stderr)
        return 2

    print(f"project: {project.name} ({project.type})")
    if task_path:
        print(f"task:    {args.taskid} -> {task_path}")
    else:
        print("task:    (none — trajectories-only analysis)")
    print(f"trajectories: {args.trajectories}")

    run_id = str(uuid.uuid4())
    harbor_dir = REPO_ROOT / "runs" / run_id / "harbor"
    harbor_dir.mkdir(parents=True, exist_ok=True)
    print(f"harbor:  {harbor_dir}")

    control = RunControl(on_progress=lambda msg: print(msg, flush=True))

    print("\n[1/1] trajectory analysis")
    selected = None
    if args.selected:
        selected = [s.strip() for s in args.selected.split(",") if s.strip()] or None
        if selected:
            print(f"selected: {len(selected)} trial dir(s)")
    try:
        result = run_trajectory_analysis(
            project, args.trajectories, task_path=task_path,
            control=control, jobs_dir=harbor_dir, selected_paths=selected,
        )
    except KeyboardInterrupt:
        print("\ninterrupted — stopping the analysis and its containers...")
        control.cancel()
        return 130

    if result.skipped:
        print(f"  skipped: {result.skip_reason}")
    else:
        print(f"  {len(result.trials)} trial(s) analyzed")
        for t in result.trials:
            fails = [c for c in t.checks if c.verdict == "fail"]
            print(f"  {t.name}: {len(t.checks) - len(fails)}/{len(t.checks)} criteria ok")

    report = compile_trajectory_report(project.name, args.taskid or "", result)

    reports_dir = REPO_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    auto_path = reports_dir / f"{args.taskid or 'trajectories'}_{run_id[:8]}.json"
    report.write(auto_path)
    print(f"\nreport written to {auto_path}")
    print(f"harbor jobs: {harbor_dir}")
    print(f"view with:  harbor view --jobs {harbor_dir}")
    print(f"\noverall: {'PASS' if report.passed else 'FAIL'}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
