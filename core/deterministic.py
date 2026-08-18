"""Deterministic checks leg: run a project's checks against a task.

Harbor projects run the repo-root `checks/` common set *in addition to* their
own `checks/`; non-Harbor projects run only the checks written for them. A
project check whose filename matches a common one shadows it, so a project can
override a shared check without editing the shared set.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .progress import RunControl
from .registry import COMMON_CHECKS_DIR, Project

CHECK_SUFFIXES = (".sh", ".py")
CHECK_TIMEOUT_SECONDS = 300


@dataclass
class CheckResult:
    name: str
    passed: bool
    output: str
    source: str = "project"  # "common" | "project"


@dataclass
class DeterministicResult:
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)


def _is_check_file(path: Path, require_prefix: bool) -> bool:
    if not path.is_file() or path.name.startswith("."):
        return False
    if path.suffix not in CHECK_SUFFIXES:
        return False
    # The common directory also holds helper scripts (rubric_review.py) and
    # fixtures, so only `check-*` files there are treated as checks.
    if require_prefix and not path.name.startswith("check-"):
        return False
    return True


def list_common_checks() -> list[Path]:
    if not COMMON_CHECKS_DIR.is_dir():
        return []
    return sorted(
        p for p in COMMON_CHECKS_DIR.iterdir() if _is_check_file(p, require_prefix=True)
    )


def list_project_checks(project: Project) -> list[Path]:
    if not project.checks_dir.is_dir():
        return []
    return sorted(
        p for p in project.checks_dir.iterdir() if _is_check_file(p, require_prefix=False)
    )


def gather_checks(project: Project) -> list[tuple[Path, str]]:
    """Return (path, source) pairs to run, project checks shadowing common ones."""
    project_checks = list_project_checks(project)
    project_names = {p.name for p in project_checks}
    common = (
        [(p, "common") for p in list_common_checks() if p.name not in project_names]
        if project.include_common_checks
        else []
    )
    return common + [(p, "project") for p in project_checks]


def run_deterministic(
    project: Project, task_path: Path, control: RunControl | None = None
) -> DeterministicResult:
    """Run every applicable check as `<check> <task_path>`; exit 0 means pass."""
    results: list[CheckResult] = []
    checks = gather_checks(project)

    for index, (check_path, source) in enumerate(checks, start=1):
        if control:
            control.raise_if_cancelled()
            control.emit(f"  ({index}/{len(checks)}) {check_path.name}")
        if check_path.suffix == ".py":
            cmd = [sys.executable, str(check_path), str(task_path)]
        else:
            cmd = ["bash", str(check_path), str(task_path)]
        try:
            proc = subprocess.run(
                cmd,
                cwd=project.root,
                capture_output=True,
                text=True,
                timeout=CHECK_TIMEOUT_SECONDS,
            )
            output = (proc.stdout + proc.stderr).strip()
            passed = proc.returncode == 0
        except subprocess.TimeoutExpired:
            output = f"check timed out after {CHECK_TIMEOUT_SECONDS}s"
            passed = False
        results.append(
            CheckResult(name=check_path.name, passed=passed, output=output, source=source)
        )

    return DeterministicResult(passed=all(r.passed for r in results), checks=results)
