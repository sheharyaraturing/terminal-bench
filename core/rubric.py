"""LLM rubric review leg: evaluate task against project rubric with extra_references."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .progress import (
    RunControl,
    tail_trial_logs,
    watch_containers,
)
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
    # Durable Harbor jobs directory (check/), when persistence was requested.
    jobs_dir: Path | None = None


# Budget for the reference blob. Delivery managers drop whole spec documents in
# extra_references/, and every byte here is either an environment variable or
# prompt tokens, so it has to be bounded.
MAX_EXTRA_REFERENCE_BYTES = 200_000
MAX_TASK_SNAPSHOT_CHARS = 200_000


def _strip_nulls(text: str) -> str:
    """NUL is valid UTF-8, so errors='replace' leaves it in place — but it is
    illegal in environment variables and meaningless to a model."""
    return text.replace("\x00", "")


def _pdf_text(path: Path) -> str | None:
    """Extract text from a PDF, or None if no extractor is available."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return None


def _reference_text(path: Path) -> str | None:
    """Readable text for one reference file, or None if it is not usable text."""
    if path.suffix.lower() == ".pdf":
        return _pdf_text(path)
    try:
        raw = path.read_bytes()
    except Exception:
        return None
    # Sniff for binary: a NUL in the first block means this is not a text file,
    # and decoding it would only produce mojibake.
    if b"\x00" in raw[:8192]:
        return None
    try:
        return raw.decode()
    except UnicodeDecodeError:
        return raw.decode(errors="replace")


def _collect_extra_references(project: Project) -> str:
    """Read extra_references/ into a single bounded, text-only context blob.

    Binary files that cannot be turned into text are named but not inlined, so
    the reviewer knows they exist rather than silently losing them.
    """
    refs_dir = project.extra_references_dir
    if not refs_dir.is_dir():
        return ""
    chunks: list[str] = []
    skipped: list[str] = []
    budget = MAX_EXTRA_REFERENCE_BYTES

    for path in sorted(refs_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        rel = path.relative_to(refs_dir)
        text = _reference_text(path)
        if text is None:
            skipped.append(f"{rel} ({path.stat().st_size:,} bytes, not readable as text)")
            continue
        text = _strip_nulls(text).strip()
        if not text:
            skipped.append(f"{rel} (no extractable text)")
            continue
        if budget <= 0:
            skipped.append(f"{rel} (reference size budget exhausted)")
            continue
        if len(text) > budget:
            text = text[:budget] + f"\n[truncated at {budget:,} characters]"
        budget -= len(text)
        chunks.append(f"--- extra_reference: {rel} ---\n{text}")

    if skipped:
        chunks.append(
            "--- extra_references not inlined ---\n" + "\n".join(skipped)
        )
    return "\n\n".join(chunks)


# `harbor check` copies the reviewed task into its wrapper task's
# environment/task/ and uploads that to the sandbox workdir (/app), so the task
# lands at /app/task. Staging the references inside the copy is what puts them
# in the container; the path below is what rubric authors write against.
EXTRA_REFERENCES_DIRNAME = "extra_references"
CONTAINER_TASK_PATH = "/app/task"
CONTAINER_REFERENCES_PATH = f"{CONTAINER_TASK_PATH}/{EXTRA_REFERENCES_DIRNAME}"

CHECK_PROMPT_PATH = REPO_ROOT / "prompts" / "check-with-references.txt"


def has_extra_references(project: Project) -> bool:
    """True when the project ships at least one real reference file."""
    refs_dir = project.extra_references_dir
    if not refs_dir.is_dir():
        return False
    return any(
        p.is_file() and not p.name.startswith(".") for p in refs_dir.rglob("*")
    )


def _stage_task_with_references(project: Project, task_path: Path, staging_root: Path) -> Path:
    """Copy the task, with extra_references/ inside it, into staging_root.

    The copy keeps the task's own directory name: harbor derives the reported
    task name and its wrapper directory from it.

    Returns the staged task directory.
    """
    staged = staging_root / task_path.name
    shutil.copytree(task_path, staged, ignore=shutil.ignore_patterns(".git"))

    dest = staged / EXTRA_REFERENCES_DIRNAME
    if dest.exists():
        # The task already has a directory by that name; don't clobber the
        # author's files, park the references beside it instead.
        dest = staged / f"{EXTRA_REFERENCES_DIRNAME}_project"
    if project.extra_references_dir.is_dir():
        shutil.copytree(
            project.extra_references_dir, dest, ignore=shutil.ignore_patterns(".git")
        )
    else:
        # The directory is always present in the container even when the project
        # ships nothing, so rubrics can reference the path unconditionally.
        dest.mkdir(parents=True)

    # An agent in a slim container cannot parse a PDF, so drop a readable
    # sibling next to any reference we can extract text from.
    for path in sorted(dest.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if _reference_text(path) is None or path.suffix.lower() not in (".pdf",):
            continue
        text = _strip_nulls(_reference_text(path) or "").strip()
        if text:
            path.with_suffix(path.suffix + ".extracted.txt").write_text(text)

    return staged


def run_rubric(
    project: Project,
    task_path: Path,
    control: RunControl | None = None,
    jobs_dir: Path | None = None,
) -> RubricResult:
    """Run the LLM rubric review for a task.

    Prefers `harbor check` when available; falls back to a local Anthropic
    review that mirrors checks/rubric_review.py but accepts a project rubric
    and extra_references context.

    When ``jobs_dir`` is set, Harbor check jobs are kept under
    ``jobs_dir/check/`` so ``harbor view --jobs <jobs_dir>`` works.
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
        result = _run_harbor_check(
            project, task_path, rubric_path, extra_refs, control, jobs_dir=jobs_dir
        )
        # A cancelled run must stop here: killing harbor looks exactly like a
        # harbor failure, and falling back would run the whole review again.
        if control:
            control.raise_if_cancelled()
        if not (result.skipped and "bad revision" in result.skip_reason):
            return result
        # fall through to direct API on harbor HEAD failure

    # Fallback: direct Anthropic call
    if control:
        control.emit("running rubric review via the Anthropic API (no container)")
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
    project: Project,
    task_path: Path,
    rubric_path: Path,
    extra_refs: str,
    control: RunControl | None = None,
    jobs_dir: Path | None = None,
) -> RubricResult:
    """Run `harbor check`, always shipping extra_references/ into the container.

    The references are staged inside a throwaway copy of the task rather than
    handed to harbor separately: harbor copies whatever directory it is given
    into the sandbox, so that copy is the only place a file can be added and be
    guaranteed to arrive.

    Harbor's ``-o`` jobs dir is durable when ``jobs_dir`` is passed
    (written under ``jobs_dir/check/``); otherwise it is a temp dir.
    """
    with tempfile.TemporaryDirectory() as tmp:
        review_path = task_path
        cmd_extra: list[str] = []
        if task_path.is_dir():
            staging_root = Path(tmp) / "staged"
            staging_root.mkdir()
            review_path = _stage_task_with_references(project, task_path, staging_root)
            if CHECK_PROMPT_PATH.is_file():
                # Tells the evaluator the references are reference material, not
                # task content it should grade.
                cmd_extra = ["-p", str(CHECK_PROMPT_PATH)]

        # -o is harbor's --jobs-dir: a directory it fills with
        # <timestamp>/check_report.json. Jobs must land *directly* in jobs_dir
        # (not jobs_dir/check/) so `harbor view --jobs <jobs_dir>` lists them.
        if jobs_dir is not None:
            harbor_jobs = jobs_dir
            harbor_jobs.mkdir(parents=True, exist_ok=True)
        else:
            harbor_jobs = Path(tmp) / "jobs"
            harbor_jobs.mkdir(parents=True, exist_ok=True)

        cmd = [
            "harbor",
            "check",
            str(review_path),
            "-r",
            str(rubric_path),
            "-o",
            str(harbor_jobs),
            *cmd_extra,
        ]
        # The evaluator agent runs inside the container and has no credentials
        # of its own; without this it fails with "Not logged in".
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            cmd += ["--ae", f"ANTHROPIC_API_KEY={api_key}"]

        output = _run_streamed(cmd, harbor_jobs, review_path.name, control)

        report_path = _latest_check_report(harbor_jobs)
        if report_path is None:
            return RubricResult(
                passed=False,
                skipped=True,
                skip_reason=f"harbor check failed: {output.strip()}",
                jobs_dir=jobs_dir,
            )
        result = _parse_check_report(report_path)
        result.jobs_dir = jobs_dir
        if control and jobs_dir is not None:
            control.emit(f"  harbor check jobs kept at {harbor_jobs}")
        return result


def _run_streamed(
    cmd: list[str], jobs_dir: Path, task_name: str, control: RunControl | None
) -> str:
    """Run harbor check, forwarding its output and the agent's actions live.

    Returns everything harbor printed, so a failure can still be reported.
    """
    if control is None:
        proc = subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=1800
        )
        return (proc.stdout or "") + (proc.stderr or "")

    control.emit(f"launching harbor check for {task_name} (this builds a container)")
    stop = threading.Event()
    watchers = [
        threading.Thread(
            target=tail_trial_logs, args=(jobs_dir, control, stop), daemon=True
        ),
        threading.Thread(
            target=watch_containers, args=(f"check-{task_name}", control, stop), daemon=True
        ),
    ]
    for w in watchers:
        w.start()

    collected: list[str] = []
    proc = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    control.register_process(proc)
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            collected.append(line)
            text = line.strip()
            # harbor redraws a progress bar with carriage returns; keep the
            # last segment so the log gets one readable line, not a smear.
            if "\r" in text:
                text = text.split("\r")[-1].strip()
            if text:
                control.emit(f"  harbor: {text[:200]}")
        proc.wait(timeout=1800)
        control.raise_if_cancelled()
    finally:
        stop.set()
        for w in watchers:
            w.join(timeout=5)
    return "".join(collected)


def _latest_check_report(jobs_dir: Path) -> Path | None:
    """Newest check_report.json under a harbor jobs directory."""
    if not jobs_dir.is_dir():
        return None
    reports = sorted(
        jobs_dir.rglob("check_report.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return reports[0] if reports else None


def _parse_check_report(path: Path) -> RubricResult:
    """Parse harbor's check_report.json.

    Shape: {"results": [{"task_name", "error", "checks": {
        "<criterion>": {"outcome": "pass|fail|not_applicable", "explanation": ...}}}]}
    """
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        return RubricResult(
            passed=False, skipped=True, skip_reason=f"invalid check_report.json: {exc}"
        )

    results = data.get("results") or []
    if not results:
        return RubricResult(
            passed=False, skipped=True, skip_reason="harbor check produced no results"
        )

    verdicts: list[CriterionVerdict] = []
    errors: list[str] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        if result.get("error"):
            # Keep it short: harbor echoes the whole agent command into `error`.
            errors.append(str(result["error"]).splitlines()[0][:300])
        for name, check in (result.get("checks") or {}).items():
            if not isinstance(check, dict):
                continue
            verdicts.append(
                CriterionVerdict(
                    name=str(name),
                    verdict=str(check.get("outcome", "fail")).lower(),
                    reason=str(check.get("explanation", "")),
                )
            )

    if not verdicts:
        reason = errors[0] if errors else "harbor check returned no criterion verdicts"
        return RubricResult(passed=False, skipped=True, skip_reason=reason)

    passed = all(v.verdict in {"pass", "not_applicable"} for v in verdicts)
    return RubricResult(passed=passed, verdicts=verdicts, raw_path=path)


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


def _read_task_snapshot(task_path: Path, max_chars: int = MAX_TASK_SNAPSHOT_CHARS) -> str:
    """Flatten a task into text. Binary assets are listed, never inlined."""
    if task_path.is_file():
        return _strip_nulls(_reference_text(task_path) or "")[:max_chars]
    chunks: list[str] = []
    binaries: list[str] = []
    for path in sorted(task_path.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        rel = path.relative_to(task_path)
        text = _reference_text(path)
        if text is None:
            binaries.append(f"{rel} ({path.stat().st_size:,} bytes)")
            continue
        chunks.append(f"--- {rel} ---\n{_strip_nulls(text)}")
    if binaries:
        chunks.append("--- binary files (not inlined) ---\n" + "\n".join(binaries))
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
