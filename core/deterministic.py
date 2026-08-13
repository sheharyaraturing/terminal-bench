"""Deterministic checks leg: run a project's checks/ against a task."""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .registry import Project


@dataclass
class CheckResult:
    name: str
    passed: bool
    output: str


@dataclass
class DeterministicResult:
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def run_deterministic(project: Project, task_path: Path) -> DeterministicResult:
    """Run every executable check in the project's checks/ directory.

    Each check is invoked as: <check> <task_path>
    A check passes if it exits 0.
    """
    results: list[CheckResult] = []
    checks_dir = project.checks_dir
    if not checks_dir.is_dir():
        return DeterministicResult(passed=True, checks=[])

    for entry in sorted(checks_dir.iterdir()):
        if entry.name.startswith(".") or entry.name == "README.md":
            continue
        if not (_is_executable(entry) or entry.suffix in {".sh", ".py"}):
            continue
        if entry.suffix == ".py":
            cmd = [sys.executable, str(entry), str(task_path)]
        else:
            cmd = ["bash", str(entry), str(task_path)]
        proc = subprocess.run(
            cmd,
            cwd=project.root,
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = (proc.stdout + proc.stderr).strip()
        results.append(
            CheckResult(name=entry.name, passed=proc.returncode == 0, output=output)
        )

    return DeterministicResult(passed=all(r.passed for r in results), checks=results)
