"""Trajectory analysis leg: evaluate Harbor trial trajectories against a rubric.

Mirrors the implementation-rubric review (`harbor exec` staging in
.github/workflows/review.yml) but the inputs are a jobs tree of trial
trajectories plus a per-project trajectory-analysis rubric, and the agent
writes per-trial verdicts plus a job-level summary to /app/verdicts.json.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .progress import RunControl, tail_trial_logs, watch_containers
from .registry import REPO_ROOT, Project

# The instruction template the analysis agent runs. Shared across projects so a
# rubric change is the only per-project knob.
INSTRUCTION_PATH = REPO_ROOT / "tools" / "trajectory-analysis" / "templates" / "instruction.md"
DOCKERFILE_PATH = REPO_ROOT / "tools" / "trajectory-analysis" / "templates" / "Dockerfile"
JOB_NAME = "trajectory-analysis"
JOB_VERDICT_JOB_NAME = "trajectory-job-verdict"
DEFAULT_IMAGE = "ubuntu:24.04"

# Placeholder in the job-level prompt where the per-trial results JSON goes.
TRIAL_RESULTS_PLACEHOLDER = "{trial_results}"

# macOS Finder/zips sprinkle these through archives; they are never trial data.
_IGNORE_NAMES = {"__MACOSX", ".DS_Store"}


def _is_ignored(name: str) -> bool:
    return name in _IGNORE_NAMES or name.startswith("._")


@dataclass
class CriterionVerdict:
    name: str
    verdict: str  # pass | fail | not_applicable
    reason: str


@dataclass
class TrialVerdict:
    name: str
    summary: str
    checks: list[CriterionVerdict] = field(default_factory=list)


@dataclass
class TrajectoryResult:
    passed: bool
    skipped: bool = False
    skip_reason: str = ""
    job_summary: str = ""
    trials: list[TrialVerdict] = field(default_factory=list)
    raw_path: Path | None = None
    # Path to the job-level verdict artifact produced by the second pass, when
    # a trajectory-analysis-prompt.txt is configured for the project.
    job_verdict_path: Path | None = None
    # Durable Harbor jobs directory (the analysis run itself), when persistence
    # was requested, so `harbor view --jobs <jobs_dir>` works after the run.
    jobs_dir: Path | None = None


def run_trajectory_analysis(
    project: Project,
    trajectories: Path,
    task_path: Path | None = None,
    control: RunControl | None = None,
    jobs_dir: Path | None = None,
    selected_paths: list[str] | None = None,
) -> TrajectoryResult:
    """Run the LLM trajectory analysis for a jobs tree of trials.

    ``trajectories`` is a path to either a ``.zip`` archive or a directory laid
    out like a Harbor ``jobs/`` tree (job dirs → trial dirs, or a flat list of
    trial dirs). When ``selected_paths`` is given, only those trial directories
    (relative paths within the tree) are analyzed; otherwise every trial dir is
    analyzed. When ``project.include_task_in_trajectory_analysis`` is true and
    ``task_path`` is given, the task is staged at
    ``/app/task-under-review/<task-name>/`` inside the container.

    When ``jobs_dir`` is set, the harbor exec job tree is kept there so
    ``harbor view --jobs <jobs_dir>`` works.
    """
    rubric_path = project.trajectory_analysis_path
    if not rubric_path.is_file():
        return TrajectoryResult(
            passed=False,
            skipped=True,
            skip_reason=f"trajectory-analysis rubric not found: {rubric_path}",
        )
    if not INSTRUCTION_PATH.is_file():
        return TrajectoryResult(
            passed=False,
            skipped=True,
            skip_reason=f"analysis instruction template not found: {INSTRUCTION_PATH}",
        )
    if not _harbor_available() or not _docker_available():
        return TrajectoryResult(
            passed=False,
            skipped=True,
            skip_reason="harbor CLI or Docker not available",
        )

    include_task = project.include_task_in_trajectory_analysis and task_path is not None

    if jobs_dir is not None:
        harbor_jobs = jobs_dir
        harbor_jobs.mkdir(parents=True, exist_ok=True)
    else:
        harbor_jobs = None

    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        traj_staged = _stage_trajectories(
            trajectories, stage / "trajectories", selected_paths
        )
        rubric_staged = stage / "rubric.toml"
        shutil.copyfile(rubric_path, rubric_staged)

        paths = [traj_staged, rubric_staged]
        if include_task:
            task_staged = _stage_task(task_path, stage / "task-under-review")
            paths.append(task_staged)
        # Ship the job-level prompt into the container so the agent can read it
        # at /app/trajectory-analysis-prompt.txt (Pass 2 renders it separately).
        prompt_path = project.trajectory_analysis_prompt_path
        if prompt_path is not None and prompt_path.is_file():
            prompt_staged = stage / "trajectory-analysis-prompt.txt"
            shutil.copyfile(prompt_path, prompt_staged)
            paths.append(prompt_staged)

        image = _build_project_image(project, control) or DEFAULT_IMAGE

        cmd = [
            "harbor",
            "exec",
        ]
        for p in paths:
            cmd += ["-p", str(p)]
        cmd += [
            "--instruction-path", str(INSTRUCTION_PATH),
            "-f", "/app/verdicts.json",
            "--image", image,
            "-a", "claude-code",
            "-m", os.environ.get("TRAJECTORY_ANALYSIS_MODEL", "sonnet"),
            "--job-name", JOB_NAME,
        ]
        if harbor_jobs is not None:
            cmd += ["--jobs-dir", str(harbor_jobs)]
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            cmd += ["--ae", f"ANTHROPIC_API_KEY={api_key}"]

        output = _run_streamed(cmd, harbor_jobs, control)
        if control:
            control.raise_if_cancelled()

        verdicts_path = _latest_verdicts(harbor_jobs) if harbor_jobs else None
        if verdicts_path is None:
            return TrajectoryResult(
                passed=False,
                skipped=True,
                skip_reason=f"harbor exec produced no verdicts.json: {output.strip()[:500]}",
                jobs_dir=jobs_dir,
            )
        result = _parse_verdicts(verdicts_path)
        result.jobs_dir = jobs_dir

        # Pass 2: job-level verdict across all trials, driven by the project's
        # trajectory-analysis-prompt.txt. Skipped when no prompt is configured.
        job_verdict = _run_job_verdict(
            project, result, control=control, jobs_dir=harbor_jobs
        )
        if job_verdict is not None:
            result.job_verdict_path = job_verdict
            narrative = job_verdict.read_text().strip()
            if narrative:
                result.job_summary = narrative

        if control and jobs_dir is not None:
            control.emit(f"  harbor exec jobs kept at {harbor_jobs}")
        return result


def _run_job_verdict(
    project: Project,
    result: TrajectoryResult,
    control: RunControl | None,
    jobs_dir: Path | None,
) -> Path | None:
    """Run the cross-trial job-level verdict pass.

    Renders the project's trajectory-analysis-prompt.txt with the per-trial
    results substituted into ``{trial_results}``, runs a second harbor exec
    whose only job is to write the overall narrative, and returns the path to
    that narrative. Returns None when no prompt is configured (single-pass).
    """
    prompt_path = project.trajectory_analysis_prompt_path
    if prompt_path is None or not prompt_path.is_file():
        if control:
            control.emit("  job-level verdict: no trajectory-analysis-prompt.txt; skipping pass 2")
        return None
    if result.skipped or not result.trials:
        return None

    trial_results = json.dumps(
        {
            t.name: {
                "summary": t.summary,
                "checks": {c.name: {"outcome": c.verdict, "explanation": c.reason} for c in t.checks},
            }
            for t in result.trials
        },
        indent=2,
    )
    template = prompt_path.read_text()
    rendered = (
        template.replace(TRIAL_RESULTS_PLACEHOLDER, trial_results)
        if TRIAL_RESULTS_PLACEHOLDER in template
        else f"{template}\n\n{trial_results}"
    )
    rendered += (
        "\n\nWrite the full job-level verdict as markdown to /app/job_verdict.md "
        "(this file is your only output; do not also print it to stdout).\n"
    )

    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        instruction = stage / "job_verdict_instruction.md"
        instruction.write_text(rendered)

        image = _build_project_image(project, control) or DEFAULT_IMAGE

        cmd = [
            "harbor",
            "exec",
            "--instruction-path", str(instruction),
            "-f", "/app/job_verdict.md",
            "--image", image,
            "-a", "claude-code",
            "-m", os.environ.get("TRAJECTORY_VERDICT_MODEL", "sonnet"),
            "--job-name", JOB_VERDICT_JOB_NAME,
        ]
        if jobs_dir is not None:
            cmd += ["--jobs-dir", str(jobs_dir)]
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            cmd += ["--ae", f"ANTHROPIC_API_KEY={api_key}"]

        if control:
            control.emit("  job-level verdict: running pass 2 across all trials")
        _run_streamed(cmd, jobs_dir, control)
        if control:
            control.raise_if_cancelled()

    verdict = _latest_file(jobs_dir, "job_verdict.md") if jobs_dir else None
    return verdict


def _stage_trajectories(
    trajectories: Path, dest: Path, selected_paths: list[str] | None = None
) -> Path:
    """Extract/copy the supplied trajectories into ``dest`` (the /app/trajectories
    mount). Accepts a .zip archive or an existing directory.

    When ``selected_paths`` is given, only files under those trial-directory
    relative paths are staged. ``__MACOSX`` / ``.DS_Store`` / ``._*`` entries
    are always dropped.
    """
    selected = None
    if selected_paths:
        selected = {p.strip("/") for p in selected_paths if p.strip("/")}

    def _wanted(rel_parts: tuple[str, ...]) -> bool:
        if any(_is_ignored(seg) for seg in rel_parts):
            return False
        if selected is None:
            return True
        rel = "/".join(rel_parts)
        # keep the file if it lives under any selected trial dir
        return any(rel == s or rel.startswith(s + "/") for s in selected)

    if trajectories.is_dir():
        dest.mkdir(parents=True)
        for entry in sorted(trajectories.rglob("*")):
            rel_parts = entry.relative_to(trajectories).parts
            if not _wanted(rel_parts):
                continue
            target = dest.joinpath(*rel_parts)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(entry, target)
        return dest
    if not trajectories.is_file() or trajectories.suffix.lower() != ".zip":
        raise ValueError(
            f"trajectories must be a .zip archive or a directory: {trajectories}"
        )
    with zipfile.ZipFile(trajectories) as zf:
        dest.mkdir(parents=True)
        for info in zf.infolist():
            if info.is_dir():
                continue
            # zip-slip guard
            rel = Path(info.filename.replace("\\", "/"))
            parts = tuple(seg for seg in rel.parts if seg not in ("", ".", ".."))
            if any(seg == ".." for seg in parts) or not parts:
                continue
            if not _wanted(parts):
                continue
            target = dest.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out, length=1024 * 1024)
    return dest


def _stage_task(task_path: Path, dest_root: Path) -> Path:
    """Copy the task into ``dest_root/<task-name>/`` so its folder name survives
    staging (harbor exec copies the directory by basename to /app/)."""
    dest_root.mkdir(parents=True, exist_ok=True)
    dest = dest_root / task_path.name
    if task_path.is_dir():
        shutil.copytree(task_path, dest, ignore=shutil.ignore_patterns(".git"))
    else:
        dest.mkdir()
        shutil.copy2(task_path, dest / task_path.name)
    return dest_root


def _harbor_available() -> bool:
    try:
        subprocess.run(["harbor", "--version"], capture_output=True, check=True, timeout=10)
        return True
    except Exception:
        return False


def _has_extra_references(project: Project) -> bool:
    refs = project.extra_references_dir
    if not refs.is_dir():
        return False
    return any(p.is_file() and not p.name.startswith(".") for p in refs.rglob("*"))


def _build_project_image(project: Project, control: RunControl | None) -> str | None:
    """Build a per-project trajectory-analysis image with extra_references baked in.

    Returns the image tag, or None to fall back to the default base image when
    the project ships no references or the build fails (never hard-fails the
    analysis over an image build problem).
    """
    if not _has_extra_references(project):
        return None
    if not DOCKERFILE_PATH.is_file():
        return None
    tag = f"trajectory-analysis:{project.name}"
    if control:
        control.emit(f"  building project image {tag} (extra_references baked in)")
    with tempfile.TemporaryDirectory() as tmp:
        ctx = Path(tmp)
        shutil.copytree(
            project.extra_references_dir,
            ctx / "extra_references",
            ignore=shutil.ignore_patterns(".git"),
        )
        try:
            proc = subprocess.run(
                ["docker", "build", "-f", str(DOCKERFILE_PATH), "-t", tag, str(ctx)],
                capture_output=True, text=True, timeout=1800,
            )
        except Exception as exc:
            if control:
                control.emit(f"  image build failed ({exc}); using {DEFAULT_IMAGE}")
            return None
        if proc.returncode != 0:
            if control:
                tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
                control.emit(f"  image build failed ({'; '.join(tail)}); using {DEFAULT_IMAGE}")
            return None
    return tag


def _docker_available() -> bool:
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True, timeout=10)
        return True
    except Exception:
        return False


def _run_streamed(cmd: list[str], jobs_dir: Path | None, control: RunControl | None) -> str:
    """Run harbor exec, forwarding its output and the agent's actions live."""
    if control is None:
        proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=3600)
        return (proc.stdout or "") + (proc.stderr or "")

    control.emit("launching harbor exec for trajectory analysis (this builds a container)")
    stop = threading.Event()
    watchers = []
    if jobs_dir is not None:
        watchers.append(threading.Thread(
            target=tail_trial_logs, args=(jobs_dir, control, stop), daemon=True
        ))
    watchers.append(threading.Thread(
        target=watch_containers, args=(JOB_NAME, control, stop), daemon=True
    ))
    for w in watchers:
        w.start()

    collected: list[str] = []
    proc = subprocess.Popen(
        cmd, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    control.register_process(proc)
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            collected.append(line)
            text = line.strip()
            if "\r" in text:
                text = text.split("\r")[-1].strip()
            if text:
                control.emit(f"  harbor: {text[:200]}")
        proc.wait(timeout=3600)
        control.raise_if_cancelled()
    finally:
        stop.set()
        for w in watchers:
            w.join(timeout=5)
    return "".join(collected)


def _latest_verdicts(jobs_dir: Path | None) -> Path | None:
    """Newest verdicts.json artifact under a harbor exec jobs directory."""
    return _latest_file(jobs_dir, "verdicts.json")


def _latest_file(jobs_dir: Path | None, name: str) -> Path | None:
    """Newest artifact with the given filename under a harbor exec jobs dir."""
    if jobs_dir is None or not jobs_dir.is_dir():
        return None
    reports = sorted(
        jobs_dir.rglob(name), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return reports[0] if reports else None


def _parse_verdicts(path: Path) -> TrajectoryResult:
    """Parse the agent's /app/verdicts.json.

    Shape:
        {"job_summary": str, "trials": {<name>: {"summary": str, "checks": {
            <criterion>: {"outcome", "explanation"}}}}}
    """
    try:
        text = path.read_text().lstrip()
        # Models occasionally leak formatting artifacts after the JSON doc.
        data = json.JSONDecoder().raw_decode(text)[0]
    except Exception as exc:
        return TrajectoryResult(
            passed=False, skipped=True,
            skip_reason=f"invalid verdicts.json: {exc}", raw_path=path,
        )

    if not isinstance(data, dict):
        return TrajectoryResult(
            passed=False, skipped=True,
            skip_reason="verdicts.json is not an object", raw_path=path,
        )

    job_summary = str(data.get("job_summary", ""))
    trials_raw = data.get("trials")
    if not isinstance(trials_raw, dict) or not trials_raw:
        return TrajectoryResult(
            passed=False, skipped=True,
            skip_reason="verdicts.json has no trials", raw_path=path,
            job_summary=job_summary,
        )

    trials: list[TrialVerdict] = []
    any_fail = False
    for name, trial in trials_raw.items():
        if not isinstance(trial, dict):
            continue
        checks: list[CriterionVerdict] = []
        for cname, check in (trial.get("checks") or {}).items():
            if not isinstance(check, dict):
                continue
            verdict = str(check.get("outcome", "fail")).lower()
            if verdict == "fail":
                any_fail = True
            checks.append(CriterionVerdict(
                name=str(cname),
                verdict=verdict,
                reason=str(check.get("explanation", "")),
            ))
        trials.append(TrialVerdict(
            name=str(name),
            summary=str(trial.get("summary", "")),
            checks=checks,
        ))

    if not trials:
        return TrajectoryResult(
            passed=False, skipped=True,
            skip_reason="verdicts.json parsed no trials", raw_path=path,
            job_summary=job_summary,
        )

    # passed = analysis completed with verdicts; not a task pass/fail gate.
    return TrajectoryResult(
        passed=True,
        job_summary=job_summary,
        trials=trials,
        raw_path=path,
    )
