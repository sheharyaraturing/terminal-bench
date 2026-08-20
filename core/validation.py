"""Validation leg: oracle/nop for Harbor projects; skip for Non-Harbor."""
from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .progress import RunControl
from .registry import Project, REPO_ROOT


@dataclass
class ValidationResult:
    passed: bool
    skipped: bool = False
    skip_reason: str = ""
    oracle_reward: float | None = None
    nop_reward: float | None = None
    details: str = ""
    # Durable Harbor jobs directory (oracle/ + nop/), when persistence was requested.
    jobs_dir: Path | None = None


def run_validation(
    project: Project,
    task_path: Path,
    control: RunControl | None = None,
    jobs_dir: Path | None = None,
) -> ValidationResult:
    """Run oracle then nop. When ``jobs_dir`` is set, Harbor job trees are kept
    there (``oracle/``, ``nop/``) so ``harbor view --jobs <jobs_dir>`` works.
    When unset, jobs land in a throwaway temp dir (previous behaviour).
    """
    if project.validation_mode == "skip" or project.type != "harbor":
        return ValidationResult(
            passed=True,
            skipped=True,
            skip_reason=f"validation skipped (mode={project.validation_mode}, type={project.type})",
        )

    if jobs_dir is not None:
        jobs_dir.mkdir(parents=True, exist_ok=True)

    if control:
        control.raise_if_cancelled()
        control.emit("  running oracle agent (expects reward 1.0)")
    oracle = _harbor_run(task_path, agent="oracle", jobs_dir=jobs_dir)
    if control:
        control.raise_if_cancelled()
        control.emit(f"  oracle reward: {oracle}")
        control.emit("  running nop agent (expects reward 0.0)")
    nop = _harbor_run(task_path, agent="nop", jobs_dir=jobs_dir)
    if control:
        control.emit(f"  nop reward: {nop}")
        if jobs_dir is not None:
            control.emit(f"  harbor jobs kept at {jobs_dir}")
            control.emit(f"  view with: harbor view --jobs {jobs_dir}")

    if oracle is None or nop is None:
        return ValidationResult(
            passed=False,
            skipped=True,
            skip_reason="harbor run failed to produce a reward (harbor/Docker unavailable?)",
            jobs_dir=jobs_dir,
        )

    passed = oracle == 1.0 and nop == 0.0
    return ValidationResult(
        passed=passed,
        oracle_reward=oracle,
        nop_reward=nop,
        details=f"oracle={oracle}, nop={nop}",
        jobs_dir=jobs_dir,
    )


def _harbor_run(
    task_path: Path, agent: str, jobs_dir: Path | None = None
) -> float | None:
    """Run one Harbor agent. Persist under ``jobs_dir/`` when given.

    Job dirs land *directly* in ``jobs_dir`` (via ``--job-name``) so
    ``harbor view --jobs <jobs_dir>`` sees them as siblings of any check jobs.
    """

    def _run(out: Path) -> float | None:
        out.mkdir(parents=True, exist_ok=True)
        cmd = [
            "harbor",
            "run",
            "-p",
            str(task_path),
            "--agent",
            agent,
            "-o",
            str(out),
            "--job-name",
            agent,
        ]
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        # Keep harbor's stderr next to the job so a failed run is diagnosable
        # even when no result.json was written.
        if proc.returncode != 0 or not list(out.rglob("result.json")):
            (out / f"{agent}.stderr.log").write_text(
                (proc.stdout or "") + (proc.stderr or "")
            )
        if proc.returncode != 0:
            return None
        return _extract_reward(out)

    if jobs_dir is not None:
        # Flat: harbor creates jobs_dir/<agent>/ itself via --job-name.
        return _run(jobs_dir)

    with tempfile.TemporaryDirectory() as tmp:
        return _run(Path(tmp))


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
