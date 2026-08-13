"""Validation leg: oracle/nop for Harbor projects; skip for Non-Harbor."""
from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .registry import Project, REPO_ROOT


@dataclass
class ValidationResult:
    passed: bool
    skipped: bool = False
    skip_reason: str = ""
    oracle_reward: float | None = None
    nop_reward: float | None = None
    details: str = ""


def run_validation(project: Project, task_path: Path) -> ValidationResult:
    if project.validation_mode == "skip" or project.type != "harbor":
        return ValidationResult(
            passed=True,
            skipped=True,
            skip_reason=f"validation skipped (mode={project.validation_mode}, type={project.type})",
        )

    oracle = _harbor_run(task_path, agent="oracle")
    nop = _harbor_run(task_path, agent="nop")

    if oracle is None or nop is None:
        return ValidationResult(
            passed=False,
            skipped=True,
            skip_reason="harbor run failed to produce a reward (harbor/Docker unavailable?)",
        )

    passed = oracle == 1.0 and nop == 0.0
    return ValidationResult(
        passed=passed,
        oracle_reward=oracle,
        nop_reward=nop,
        details=f"oracle={oracle}, nop={nop}",
    )


def _harbor_run(task_path: Path, agent: str) -> float | None:
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            "harbor",
            "run",
            "-p",
            str(task_path),
            "--agent",
            agent,
            "-o",
            tmp,
        ]
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        if proc.returncode != 0:
            return None
        return _extract_reward(Path(tmp))


def _extract_reward(run_dir: Path) -> float | None:
    for candidate in run_dir.rglob("reward.txt"):
        try:
            return float(candidate.read_text().strip())
        except Exception:
            continue
    for candidate in run_dir.rglob("result.json"):
        try:
            data = json.loads(candidate.read_text())
        except Exception:
            continue
        if isinstance(data, dict) and "reward" in data:
            try:
                return float(data["reward"])
            except Exception:
                continue
    return None
