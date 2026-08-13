"""LLM rubric review leg: evaluate task against project rubric with extra_references."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .registry import Project, REPO_ROOT


@dataclass
class CriterionVerdict:
    name: str
    verdict: str  # pass | fail | not_applicable
    reason: str


@dataclass
class RubricResult:
    passed: bool
    verdicts: list[CriterionVerdict] = field(default_factory=list)
    raw_path: Path | None = None
    skipped: bool = False
    skip_reason: str = ""


def _collect_extra_references(project: Project) -> str:
    """Read extra_references/ into a single context blob for the reviewer."""
    refs_dir = project.extra_references_dir
    if not refs_dir.is_dir():
        return ""
    chunks: list[str] = []
    for path in sorted(refs_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        try:
            text = path.read_text(errors="replace")
        except Exception:
            continue
        rel = path.relative_to(refs_dir)
        chunks.append(f"--- extra_reference: {rel} ---\n{text}")
    return "\n\n".join(chunks)


def run_rubric(project: Project, task_path: Path) -> RubricResult:
    """Run the LLM rubric review for a task.

    Prefers `harbor check` when available; falls back to a local Anthropic
    review that mirrors checks/rubric_review.py but accepts a project rubric
    and extra_references context.
    """
    rubric_path = project.rubric_path
    if not rubric_path.is_file():
        return RubricResult(
            passed=False,
            skipped=True,
            skip_reason=f"rubric not found: {rubric_path}",
        )

    extra_refs = _collect_extra_references(project)

    # harbor check only supports Harbor-format task directories and needs Docker
    if project.type == "harbor" and _harbor_available() and _docker_available():
        result = _run_harbor_check(project, task_path, rubric_path, extra_refs)
        if not (result.skipped and "bad revision" in result.skip_reason):
            return result
        # fall through to direct API on harbor HEAD failure

    # Fallback: direct Anthropic call
    return _run_anthropic_check(project, task_path, rubric_path, extra_refs)


def _harbor_available() -> bool:
    try:
        subprocess.run(
            ["harbor", "--version"],
            capture_output=True,
            check=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


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


def _run_harbor_check(
    project: Project, task_path: Path, rubric_path: Path, extra_refs: str
) -> RubricResult:
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "verdicts.json"
        cmd = [
            "harbor",
            "check",
            str(task_path),
            "-r",
            str(rubric_path),
            "-o",
            str(out_path),
        ]
        env = os.environ.copy()
        if extra_refs:
            env["AUTOREVIEWER_EXTRA_REFERENCES"] = extra_refs
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=env,
            timeout=1800,
        )
        if not out_path.is_file():
            return RubricResult(
                passed=False,
                skipped=True,
                skip_reason=f"harbor check failed: {proc.stderr.strip() or proc.stdout.strip()}",
            )
        return _parse_verdicts(out_path)


def _run_anthropic_check(
    project: Project, task_path: Path, rubric_path: Path, extra_refs: str
) -> RubricResult:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return RubricResult(
            passed=False,
            skipped=True,
            skip_reason="ANTHROPIC_API_KEY not set and harbor CLI not available",
        )

    try:
        import anthropic
    except ImportError:
        return RubricResult(
            passed=False,
            skipped=True,
            skip_reason="anthropic package not installed",
        )

    rubric_text = rubric_path.read_text()
    task_text = _read_task_snapshot(task_path)
    system = (
        "You are a strict task reviewer. Evaluate the task against each rubric "
        "criterion. Return JSON: a list of objects with name, verdict "
        "(pass|fail|not_applicable), and reason."
    )
    user_parts = [f"Rubric:\n{rubric_text}", f"Task:\n{task_text}"]
    if extra_refs:
        user_parts.append(f"Extra references:\n{extra_refs}")
    user = "\n\n".join(user_parts)

    client = anthropic.Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except Exception as exc:
        return RubricResult(
            passed=False,
            skipped=True,
            skip_reason=f"anthropic API error: {exc}",
        )
    text = "".join(block.text for block in resp.content if hasattr(block, "text"))
    return _parse_verdicts_from_text(text)


def _read_task_snapshot(task_path: Path, max_chars: int = 200_000) -> str:
    if task_path.is_file():
        return task_path.read_text(errors="replace")[:max_chars]
    chunks: list[str] = []
    for path in sorted(task_path.rglob("*")):
        if path.is_file() and not path.name.startswith("."):
            rel = path.relative_to(task_path)
            try:
                chunks.append(f"--- {rel} ---\n{path.read_text(errors='replace')}")
            except Exception:
                continue
    return "\n\n".join(chunks)[:max_chars]


def _parse_verdicts(path: Path) -> RubricResult:
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        return RubricResult(
            passed=False, skipped=True, skip_reason=f"invalid verdicts.json: {exc}"
        )
    return _parse_verdicts_data(data, raw_path=path)


def _parse_verdicts_from_text(text: str) -> RubricResult:
    # Extract first JSON array/object from model output
    start = text.find("[")
    if start == -1:
        start = text.find("{")
    if start == -1:
        return RubricResult(
            passed=False, skipped=True, skip_reason="no JSON in model response"
        )
    decoder = json.JSONDecoder()
    try:
        data, _ = decoder.raw_decode(text[start:])
    except Exception as exc:
        return RubricResult(
            passed=False, skipped=True, skip_reason=f"could not parse model JSON: {exc}"
        )
    return _parse_verdicts_data(data)


def _parse_verdicts_data(data, raw_path: Path | None = None) -> RubricResult:
    items = data
    if isinstance(data, dict):
        for key in ("verdicts", "criteria", "results"):
            if key in data:
                items = data[key]
                break
    verdicts: list[CriterionVerdict] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        verdicts.append(
            CriterionVerdict(
                name=str(item.get("name", "unknown")),
                verdict=str(item.get("verdict", item.get("status", "fail"))).lower(),
                reason=str(item.get("reason", item.get("explanation", ""))),
            )
        )
    passed = all(v.verdict in {"pass", "not_applicable"} for v in verdicts)
    return RubricResult(passed=passed, verdicts=verdicts, raw_path=raw_path)
