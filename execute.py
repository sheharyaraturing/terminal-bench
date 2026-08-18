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
import threading
import time
import uuid
from pathlib import Path

from core.deterministic import run_deterministic
from core.registry import REPO_ROOT, list_projects, load_project, resolve_task
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


def _heartbeat_loop(stop_event: threading.Event, interval: int = 15) -> None:
    """Print container status every `interval` seconds until stopped."""
    start = time.time()
    while not stop_event.is_set():
        elapsed = int(time.time() - start)
        if not _docker_available():
            print(f"\r  [heartbeat {elapsed:4d}s] Docker not available", end="", flush=True)
        else:
            proc = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
            )
            names = [n for n in proc.stdout.splitlines() if "check-" in n or "rubric" in n]
            if not names:
                print(f"\r  [heartbeat {elapsed:4d}s] no review containers", end="", flush=True)
            else:
                name = names[0]
                try:
                    log = subprocess.run(
                        ["docker", "exec", name, "tail", "-c", "2000", "/logs/agent/claude-code.txt"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    tokens = "?"
                    tools = "?"
                    if log.returncode == 0:
                        import re
                        m = re.findall(r'"estimated_tokens":(\d+)', log.stdout)
                        if m:
                            tokens = m[-1]
                        tools = str(log.stdout.count('"type":"tool_use"'))
                    print(
                        f"\r  [heartbeat {elapsed:4d}s] {name} tokens={tokens} tool_calls={tools}",
                        end="",
                        flush=True,
                    )
                except Exception:
                    print(f"\r  [heartbeat {elapsed:4d}s] {name} (log unavailable)", end="", flush=True)
        stop_event.wait(interval)
    print()  # newline after last heartbeat


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

    print("\n[1/3] deterministic checks")
    det = run_deterministic(project, task_path)
    for c in det.checks:
        status = "PASS" if c.passed else "FAIL"
        print(f"  {status}  [{c.source}] {c.name}")
    if not det.checks:
        print("  (no checks)")

    print("\n[2/3] LLM rubric review")
    stop_heartbeat = threading.Event()
    heartbeat = threading.Thread(target=_heartbeat_loop, args=(stop_heartbeat,), daemon=True)
    heartbeat.start()
    try:
        rub = run_rubric(project, task_path)
    finally:
        stop_heartbeat.set()
        heartbeat.join(timeout=5)
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

    # Always write to reports/<task_id>_<uuid>.json
    reports_dir = REPO_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    auto_path = reports_dir / f"{args.taskid}_{uuid.uuid4().hex[:8]}.json"
    report.write(auto_path)
    print(f"\nreport written to {auto_path}")

    # Also write to user-specified path if provided
    if args.output:
        report.write(args.output)
        print(f"report also written to {args.output}")

    print(f"\noverall: {'PASS' if report.passed else 'FAIL'}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
