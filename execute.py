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
from pathlib import Path

from core.deterministic import run_deterministic
from core.registry import list_projects, load_project, resolve_task
from core.report import compile_report
from core.rubric import run_rubric
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
        "--gates",
        action="store_true",
        help="Run the full three-gate QA flow via run-qa-gates.sh",
    )
    parser.add_argument(
        "--skip-review",
        action="store_true",
        help="With --gates: skip Gate 2 (LLM rubric review)",
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="With --gates: skip Gate 3 (oracle/nop validation)",
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

    if args.list_projects:
        for p in list_projects():
            print(f"{p.name}\t{p.type}\t{p.root}")
        return 0

    if not args.project or not args.taskid:
        print("error: --project and --taskid are required", file=sys.stderr)
        return 2

    if args.gates:
        import subprocess

        cmd = ["bash", "run-qa-gates.sh", args.project, args.taskid]
        if args.skip_review:
            cmd.append("--skip-review")
        if args.skip_validate:
            cmd.append("--skip-validate")
        return subprocess.run(cmd, cwd=Path(__file__).resolve().parent).returncode

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

    print("\n[1/3] deterministic checks")
    det = run_deterministic(project, task_path)
    for c in det.checks:
        status = "PASS" if c.passed else "FAIL"
        print(f"  {status}  {c.name}")
    if not det.checks:
        print("  (no checks)")

    print("\n[2/3] LLM rubric review")
    rub = run_rubric(project, task_path)
    if rub.skipped:
        print(f"  skipped: {rub.skip_reason}")
    else:
        for v in rub.verdicts:
            print(f"  {v.verdict.upper()}  {v.name}: {v.reason}")

    print("\n[3/3] validation")
    val = run_validation(project, task_path)
    if val.skipped:
        print(f"  skipped: {val.skip_reason}")
    else:
        print(f"  oracle={val.oracle_reward} nop={val.nop_reward} {val.details}")

    report = compile_report(project.name, args.taskid, det, rub, val)
    if args.output:
        report.write(args.output)
        print(f"\nreport written to {args.output}")

    print(f"\noverall: {'PASS' if report.passed else 'FAIL'}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
