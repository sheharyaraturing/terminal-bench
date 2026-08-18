"""Report compiler: merge pipeline legs into a single PASS/FAIL report."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .deterministic import DeterministicResult
from .rubric import RubricResult
from .validation import ValidationResult


@dataclass
class EvaluationReport:
    project: str
    task_id: str
    passed: bool
    deterministic: dict
    rubric: dict
    validation: dict

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    def write(self, path: Path) -> None:
        path.write_text(self.to_json() + "\n")


def compile_report(
    project_name: str,
    task_id: str,
    deterministic: DeterministicResult,
    rubric: RubricResult,
    validation: ValidationResult,
) -> EvaluationReport:
    det = {
        "passed": deterministic.passed,
        "applicable": bool(deterministic.checks),
        "checks": [
            {"name": c.name, "source": c.source, "passed": c.passed, "output": c.output}
            for c in deterministic.checks
        ],
    }
    rub = {
        "passed": rubric.passed,
        "applicable": not rubric.skipped,
        "skipped": rubric.skipped,
        "skip_reason": rubric.skip_reason,
        "verdicts": [
            {"name": v.name, "verdict": v.verdict, "reason": v.reason}
            for v in rubric.verdicts
        ],
    }
    val = {
        "passed": validation.passed,
        "applicable": not validation.skipped,
        "skipped": validation.skipped,
        "skip_reason": validation.skip_reason,
        "oracle_reward": validation.oracle_reward,
        "nop_reward": validation.nop_reward,
        "details": validation.details,
    }
    passed = (
        (not det["applicable"] or deterministic.passed)
        and (not rub["applicable"] or rubric.passed)
        and (not val["applicable"] or validation.passed)
    )
    return EvaluationReport(
        project=project_name,
        task_id=task_id,
        passed=passed,
        deterministic=det,
        rubric=rub,
        validation=val,
    )
