"""LLM rubric review leg: evaluate task against project rubric with extra_references."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
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
    # How many reviewers marked this criterion "fail", out of how many valid
    # reviews judged it. A single-review verdict leaves these at 0.
    fail_votes: int = 0
    votes: int = 0


@dataclass
class ReviewerResult:
    """One independent reviewer's verdicts, or the reason it produced none."""

    label: str
    verdicts: list[CriterionVerdict] = field(default_factory=list)
    error: str = ""
    trial_dir: Path | None = None


@dataclass
class RubricResult:
    passed: bool
    # The consensus verdicts: a criterion is "fail" only when at least
    # min_fail_votes reviewers flagged it.
    verdicts: list[CriterionVerdict] = field(default_factory=list)
    raw_path: Path | None = None
    skipped: bool = False
    skip_reason: str = ""
    # Durable Harbor jobs directory (check/), when persistence was requested.
    jobs_dir: Path | None = None
    reviewers: list[ReviewerResult] = field(default_factory=list)
    min_fail_votes: int = 1
    # Failures some reviewer reported that did not reach min_fail_votes. They
    # do not affect `passed`; they are kept so a reader can see the dissent.
    flagged: list[CriterionVerdict] = field(default_factory=list)
    cost_usd: float | None = None


def combine_reviews(reviewers: list[ReviewerResult], min_fail_votes: int) -> RubricResult:
    """Merge independent reviews: a criterion fails when >= min_fail_votes flag it.

    Reviewers that errored are left out of the vote. If fewer valid reviews
    came back than min_fail_votes, no criterion could ever reach consensus, so
    the review is reported as skipped rather than silently passing.
    """
    valid = [r for r in reviewers if not r.error and r.verdicts]
    if not valid or len(valid) < min_fail_votes:
        errors = "; ".join(f"{r.label}: {r.error}" for r in reviewers if r.error)
        return RubricResult(
            passed=False,
            skipped=True,
            skip_reason=(
                f"only {len(valid)} of {len(reviewers)} reviewers returned a valid "
                f"review (need at least {max(min_fail_votes, 1)})"
                + (f" — {errors}" if errors else "")
            ),
            reviewers=reviewers,
            min_fail_votes=min_fail_votes,
        )

    # Criterion order follows the rubric, as the first valid reviewer saw it.
    names: list[str] = []
    by_name: dict[str, list[tuple[str, CriterionVerdict]]] = {}
    for reviewer in valid:
        for v in reviewer.verdicts:
            if v.name not in by_name:
                names.append(v.name)
                by_name[v.name] = []
            by_name[v.name].append((reviewer.label, v))

    verdicts: list[CriterionVerdict] = []
    flagged: list[CriterionVerdict] = []
    for name in names:
        votes = by_name[name]
        fails = [(label, v) for label, v in votes if v.verdict == "fail"]
        fail_reason = "\n".join(f"[{label}] {v.reason}" for label, v in fails)
        if len(fails) >= min_fail_votes:
            verdicts.append(
                CriterionVerdict(name, "fail", fail_reason, len(fails), len(votes))
            )
            continue
        # Not a consensus failure: report the most common non-fail outcome
        # (ties go to "pass"), with the reason one of those reviewers gave.
        others = [v for _, v in votes if v.verdict != "fail"]
        n_na = sum(1 for v in others if v.verdict == "not_applicable")
        outcome = "not_applicable" if n_na > len(others) - n_na else "pass"
        reason = next((v.reason for v in others if v.verdict == outcome), "")
        verdicts.append(CriterionVerdict(name, outcome, reason, len(fails), len(votes)))
        if fails:
            flagged.append(
                CriterionVerdict(name, "fail", fail_reason, len(fails), len(votes))
            )

    return RubricResult(
        passed=all(v.verdict != "fail" for v in verdicts),
        verdicts=verdicts,
        reviewers=reviewers,
        min_fail_votes=min_fail_votes,
        flagged=flagged,
    )


def review_settings(project: Project) -> tuple[int, int]:
    """(reviewers, min_fail_votes) for a project, with env overrides applied.

    Clamped so the vote is always winnable: at least one reviewer, and a
    threshold between 1 and the number of reviewers.
    """
    reviewers = int(os.environ.get("RUBRIC_REVIEWERS") or project.rubric_reviewers)
    min_votes = int(
        os.environ.get("RUBRIC_MIN_FAIL_VOTES") or project.rubric_min_fail_votes
    )
    reviewers = max(1, reviewers)
    return reviewers, min(max(1, min_votes), reviewers)


def format_rubric_lines(result: RubricResult) -> list[str]:
    """Human-readable lines for a finished rubric review (CLI and API log)."""
    lines: list[str] = []
    n_valid = sum(1 for r in result.reviewers if not r.error and r.verdicts)
    if len(result.reviewers) > 1:
        lines.append(
            f"consensus of {n_valid}/{len(result.reviewers)} reviewers — a criterion "
            f"fails when at least {result.min_fail_votes} flag it"
        )
    for v in result.verdicts:
        tally = f" ({v.fail_votes}/{v.votes} flagged)" if len(result.reviewers) > 1 else ""
        lines.append(f"{v.verdict.upper()}{tally}  {v.name}: {v.reason}")
    if result.flagged:
        lines.append(
            f"flagged by fewer than {result.min_fail_votes} reviewers (not counted):"
        )
        for v in result.flagged:
            lines.append(f"  {v.name} ({v.fail_votes}/{v.votes}): {v.reason}")
    if len(result.reviewers) > 1:
        for r in result.reviewers:
            where = f" [{r.trial_dir}]" if r.trial_dir else ""
            if r.error:
                lines.append(f"reviewer {r.label}: error — {r.error.splitlines()[0][:200]}{where}")
            else:
                failed = [v.name for v in r.verdicts if v.verdict == "fail"]
                lines.append(
                    f"reviewer {r.label}: fails {', '.join(failed) or 'nothing'}{where}"
                )
    if result.cost_usd is not None:
        lines.append(f"review cost: ${result.cost_usd:.2f}")
    return lines


# Budget for the reference blob. Delivery managers drop whole spec documents in
# extra_references/, and every byte here is either an environment variable or
# prompt tokens, so it has to be bounded.
MAX_EXTRA_REFERENCE_BYTES = 200_000
MAX_TASK_SNAPSHOT_CHARS = 200_000

# Outer cap on a single `harbor check` invocation (container build + agent setup
# + evaluator run). 50 min leaves room for slow in-container installs.
HARBOR_CHECK_TIMEOUT_SEC = 3000


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


def _render_check_prompt(rubric_path: Path) -> str:
    """The check prompt with the whole rubric file in place of {criteria_guidance}.

    harbor renders {criteria_guidance} as just "- name: guidance" per criterion,
    dropping descriptions and comments — and the comments carry guidance the
    evaluator needs. Braces are doubled because harbor runs the result through
    str.format_map, which would otherwise eat TOML/JSON braces in the rubric.
    """
    rubric_text = rubric_path.read_text().replace("{", "{{").replace("}", "}}")
    return CHECK_PROMPT_PATH.read_text().replace("{criteria_guidance}", rubric_text)


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
    n_reviewers, min_fail_votes = review_settings(project)
    if control and n_reviewers > 1:
        control.emit(
            f"running {n_reviewers} independent reviewers; a criterion fails when "
            f"at least {min_fail_votes} flag it"
        )

    # harbor check only supports Harbor-format task directories and needs Docker
    if project.type == "harbor" and _harbor_available() and _docker_available():
        result = _run_harbor_check(
            project, task_path, rubric_path, extra_refs, control, jobs_dir=jobs_dir,
            n_reviewers=n_reviewers, min_fail_votes=min_fail_votes,
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
    return _run_anthropic_check(
        project, task_path, rubric_path, extra_refs, n_reviewers, min_fail_votes
    )


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
    n_reviewers: int = 1,
    min_fail_votes: int = 1,
) -> RubricResult:
    """Run `harbor check`, always shipping extra_references/ into the container.

    With ``n_reviewers`` > 1 harbor runs that many independent review trials
    (``-k``) side by side (``-n``); their verdicts are merged by
    :func:`combine_reviews`.

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
                prompt_path = Path(tmp) / "check-prompt.txt"
                prompt_path.write_text(_render_check_prompt(rubric_path))
                cmd_extra = ["-p", str(prompt_path)]

        # -o is harbor's --jobs-dir: a directory it fills with
        # <timestamp>/check_report.json. Jobs must land *directly* in jobs_dir
        # (not jobs_dir/check/) so `harbor view --jobs <jobs_dir>` lists them.
        if jobs_dir is not None:
            harbor_jobs = jobs_dir
            harbor_jobs.mkdir(parents=True, exist_ok=True)
        else:
            harbor_jobs = Path(tmp) / "jobs"
            harbor_jobs.mkdir(parents=True, exist_ok=True)

        # Installing the claude-code agent inside a slim container (apt-get
        # nodejs/npm + downloading claude-code) can exceed Harbor's default
        # 360s agent-setup timeout on slow networks, so raise it.
        setup_multiplier = os.environ.get("HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER", "3.0")
        config_path = Path(tmp) / "harbor-check-config.yaml"
        config_path.write_text(
            f"agent_setup_timeout_multiplier: {setup_multiplier}\n"
        )

        cmd = [
            "harbor",
            "check",
            str(review_path),
            "-r",
            str(rubric_path),
            "-o",
            str(harbor_jobs),
            "-c",
            str(config_path),
            "--model",
            os.environ.get("HARBOR_CHECK_MODEL", "claude-opus-5"),
            # Independent reviewers, all running at once.
            "-k",
            str(n_reviewers),
            "-n",
            str(n_reviewers),
            *cmd_extra,
        ]
        # Select the Harbor environment backend (docker | modal | daytona | e2b |
        # runloop | gke | apple-container). Unset = Harbor's default (docker), so
        # existing local-docker runs are unchanged. Set HARBOR_ENV_BACKEND=daytona
        # (etc.) to run the rubric evaluator in a remote backend instead of local
        # Docker. Requires the matching harbor extra, e.g. harbor[daytona].
        env_backend = os.environ.get("HARBOR_ENV_BACKEND", "").strip()
        if env_backend:
            cmd += ["--env", env_backend]
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
        result = _parse_check_report(report_path, min_fail_votes)
        result.jobs_dir = jobs_dir
        if jobs_dir is None:
            # The trial dirs live in a temp dir that is about to be deleted.
            for reviewer in result.reviewers:
                reviewer.trial_dir = None
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
            cmd, cwd=REPO_ROOT, capture_output=True, text=True,
            timeout=HARBOR_CHECK_TIMEOUT_SEC,
        )
        return (proc.stdout or "") + (proc.stderr or "")

    env_backend = os.environ.get("HARBOR_ENV_BACKEND", "").strip() or "default (unset → harbor chooses)"
    control.emit(
        f"launching harbor check for {task_name} (this builds a container) "
        f"[env: {env_backend}]"
    )
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
        proc.wait(timeout=HARBOR_CHECK_TIMEOUT_SEC)
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


def _verdicts_from_checks(checks: dict) -> list[CriterionVerdict]:
    """{"<criterion>": {"outcome", "explanation"}} -> verdicts, in file order."""
    verdicts: list[CriterionVerdict] = []
    for name, check in (checks or {}).items():
        if not isinstance(check, dict):
            continue
        verdicts.append(
            CriterionVerdict(
                name=str(name),
                verdict=str(check.get("outcome", "fail")).lower(),
                reason=str(check.get("explanation", "")),
            )
        )
    return verdicts


def _reviewers_from_trials(job_dir: Path) -> list[ReviewerResult]:
    """One ReviewerResult per `harbor check` trial dir in a job.

    Read from the trial dirs rather than check_report.json because the report
    drops the trial name, and the trial name is what ties a reviewer's verdicts
    to its logs and trajectory. Validity mirrors harbor's own rule: no trial
    exception, verifier reward 1, and a check-result.json artifact.
    """
    reviewers: list[ReviewerResult] = []
    for trial_dir in sorted(job_dir.iterdir()):
        result_path = trial_dir / "result.json"
        if not trial_dir.name.startswith("check-") or not result_path.is_file():
            continue
        label = trial_dir.name.rsplit("__", 1)[-1]
        try:
            trial = json.loads(result_path.read_text())
        except Exception as exc:
            reviewers.append(ReviewerResult(label, error=f"unreadable result.json: {exc}", trial_dir=trial_dir))
            continue
        exc_info = trial.get("exception_info")
        if exc_info:
            message = str(exc_info.get("exception_message", "")).splitlines()
            reviewers.append(
                ReviewerResult(
                    label,
                    error=f"{exc_info.get('exception_type', 'error')}: {message[0] if message else ''}",
                    trial_dir=trial_dir,
                )
            )
            continue
        rewards = (trial.get("verifier_result") or {}).get("rewards") or {}
        checks_path = trial_dir / "artifacts" / "check-result.json"
        if rewards.get("reward") != 1 or not checks_path.is_file():
            stdout = trial_dir / "verifier" / "test-stdout.txt"
            why = stdout.read_text().strip() if stdout.is_file() else "no verifier output"
            reviewers.append(
                ReviewerResult(label, error=f"no valid result: {why[:300]}", trial_dir=trial_dir)
            )
            continue
        try:
            verdicts = _verdicts_from_checks(json.loads(checks_path.read_text()))
        except Exception as exc:
            reviewers.append(ReviewerResult(label, error=f"invalid check-result.json: {exc}", trial_dir=trial_dir))
            continue
        reviewers.append(ReviewerResult(label, verdicts=verdicts, trial_dir=trial_dir))
    return reviewers


def _parse_check_report(path: Path, min_fail_votes: int = 1) -> RubricResult:
    """Parse a finished `harbor check` job into a consensus RubricResult.

    check_report.json shape: {"results": [{"task_name", "error", "cost_usd",
    "checks": {"<criterion>": {"outcome": "pass|fail|not_applicable",
    "explanation": ...}}}]} — one entry per reviewer (harbor's -k).
    """
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        return RubricResult(
            passed=False, skipped=True, skip_reason=f"invalid check_report.json: {exc}"
        )

    results = [r for r in (data.get("results") or []) if isinstance(r, dict)]
    if not results:
        return RubricResult(
            passed=False, skipped=True, skip_reason="harbor check produced no results"
        )

    reviewers = _reviewers_from_trials(path.parent)
    if not reviewers:
        # No trial dirs to read (unexpected layout): fall back to the report,
        # which has the same verdicts but no trial names.
        reviewers = [
            ReviewerResult(
                f"reviewer-{i}",
                verdicts=_verdicts_from_checks(r.get("checks") or {}),
                # Keep it short: harbor echoes the whole agent command into `error`.
                error=str(r.get("error") or "").splitlines()[0][:300] if r.get("error") else "",
            )
            for i, r in enumerate(results, 1)
        ]

    result = combine_reviews(reviewers, min_fail_votes)
    result.raw_path = path
    costs = [r["cost_usd"] for r in results if isinstance(r.get("cost_usd"), (int, float))]
    result.cost_usd = sum(costs) if costs else None
    return result


def _run_anthropic_check(
    project: Project,
    task_path: Path,
    rubric_path: Path,
    extra_refs: str,
    n_reviewers: int = 1,
    min_fail_votes: int = 1,
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
        "criterion. Return ONLY a JSON array of objects with name, verdict "
        "(pass|fail|not_applicable), and reason. Do not write any prose before "
        "or after the JSON."
    )
    user_parts = [f"Rubric:\n{rubric_text}", f"Task:\n{task_text}"]
    if extra_refs:
        user_parts.append(f"Extra references:\n{extra_refs}")
    user = "\n\n".join(user_parts)

    model = os.environ.get("HARBOR_CHECK_MODEL", "claude-opus-5")
    client = anthropic.Anthropic(api_key=api_key)

    def review(label: str) -> ReviewerResult:
        try:
            # Stream the response: the Anthropic SDK rejects non-streaming
            # requests that may exceed 10 minutes, and a large rubric + task
            # snapshot with a big output budget routinely crosses that line.
            pieces: list[str] = []
            with client.messages.stream(
                model=model,
                max_tokens=32000,
                system=system,
                messages=[{"role": "user", "content": user}],
            ) as stream:
                for chunk in stream.text_stream:
                    pieces.append(chunk)
                final = stream.get_final_message()
            text = "".join(pieces) or "".join(
                block.text for block in final.content if hasattr(block, "text")
            )
        except Exception as exc:
            return ReviewerResult(label, error=f"anthropic API error: {exc}")
        parsed = _parse_verdicts_from_text(text)
        if parsed.skipped:
            return ReviewerResult(label, error=parsed.skip_reason)
        return ReviewerResult(label, verdicts=parsed.verdicts)

    # Independent calls, run side by side like harbor's -k trials.
    labels = [f"api-{i}" for i in range(1, n_reviewers + 1)]
    with ThreadPoolExecutor(max_workers=n_reviewers) as pool:
        reviewers = list(pool.map(review, labels))
    return combine_reviews(reviewers, min_fail_votes)


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
