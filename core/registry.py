"""Project registry: discover, create, and resolve tasks for projects."""
from __future__ import annotations

import re
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECTS_ROOT = REPO_ROOT / "projects"
COMMON_CHECKS_DIR = REPO_ROOT / "checks"

PROJECT_TYPES = ("harbor", "non-harbor")
VALIDATION_MODES = ("oracle_nop", "skip")

# Scaffold folders that live alongside real projects but must never be treated
# as one (they have no content and would show up in every project listing).
TEMPLATE_SUFFIX = "-project-template"

# Project names become directory names, so they are restricted hard. This is
# the single guard against path traversal for every API path built from a
# user-supplied project name.
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")


@dataclass(frozen=True)
class Project:
    name: str
    type: str  # "harbor" | "non-harbor"
    description: str
    root: Path
    tasks_dir: Path
    checks_dir: Path
    rubric_path: Path
    extra_references_dir: Path
    validation_mode: str  # "oracle_nop" | "skip"
    include_common_checks: bool
    # Per-project trajectory-analysis rubric (Harbor jobs trees). Defaults to a
    # sibling of the implementation rubric so a project only has to opt in by
    # dropping the file in rubrics/.
    trajectory_analysis_path: Path
    # Optional per-project prompt for the job-level (cross-trial) verdict pass.
    # Defaults to a trajectory-analysis-prompt.txt sibling of the trajectory
    # rubric; None means the analysis stays single-pass (per-trial only).
    trajectory_analysis_prompt_path: Path | None = None
    # Whether the task-under-review is copied into the analysis container.
    # Some criteria (task_specification, difficulty_crux) need the task files;
    # trajectories-only runs can set this false.
    include_task_in_trajectory_analysis: bool = True


def _load_toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def validate_project_name(name: str) -> str:
    """Return `name` if it is a safe project/directory name, else raise."""
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ValueError(
            f"invalid project name: {name!r} "
            "(use 2-64 chars: lowercase letters, digits, hyphens; must start alphanumeric)"
        )
    if name.endswith(TEMPLATE_SUFFIX):
        raise ValueError(f"reserved project name: {name!r}")
    return name


def is_template_dir(path: Path) -> bool:
    return path.name.endswith(TEMPLATE_SUFFIX)


def list_projects() -> list[Project]:
    """Discover all projects under projects/<type>/<name>/project.toml."""
    projects: list[Project] = []
    if not PROJECTS_ROOT.is_dir():
        return projects
    for type_dir in sorted(PROJECTS_ROOT.iterdir()):
        if not type_dir.is_dir():
            continue
        for proj_dir in sorted(type_dir.iterdir()):
            if not proj_dir.is_dir() or is_template_dir(proj_dir):
                continue
            if (proj_dir / "project.toml").is_file():
                projects.append(_project_from_dir(proj_dir, type_dir.name))
    return projects


def load_project(name: str) -> Project:
    """Load a project by name, searching projects/*/<name>/project.toml."""
    for type_dir in sorted(PROJECTS_ROOT.iterdir()):
        if not type_dir.is_dir():
            continue
        proj_dir = type_dir / name
        if is_template_dir(proj_dir):
            continue
        if (proj_dir / "project.toml").is_file():
            return _project_from_dir(proj_dir, type_dir.name)
    raise FileNotFoundError(f"project not found: {name}")


def project_exists(name: str) -> bool:
    try:
        load_project(name)
        return True
    except (FileNotFoundError, ValueError):
        return False


def _project_from_dir(proj_dir: Path, type_default: str) -> Project:
    data = _load_toml(proj_dir / "project.toml")
    proj = data.get("project", {})
    paths = data.get("paths", {})
    checks = data.get("checks", {})
    validation = data.get("validation", {})
    trajectory = data.get("trajectory_analysis", {})
    ptype = proj.get("type", type_default)
    rubrics_path = proj_dir / paths.get("rubrics", "rubrics/rubrics.toml")
    trajectory_rubric_path = (
        proj_dir / paths["trajectory_analysis"]
        if paths.get("trajectory_analysis")
        else (
            rubrics_path.parent / "trajectory-analysis.toml"
            if rubrics_path.name != "rubrics.toml"
            else REPO_ROOT / "rubrics" / "trial-analysis.toml"
        )
    )
    # Job-level verdict prompt: explicit path, else a
    # trajectory-analysis-prompt.txt sibling of the trajectory rubric, else None
    # (analysis stays single-pass).
    prompt_path = (
        proj_dir / paths["trajectory_analysis_prompt"]
        if paths.get("trajectory_analysis_prompt")
        else trajectory_rubric_path.parent / "trajectory-analysis-prompt.txt"
    )
    trajectory_prompt = prompt_path if prompt_path.is_file() else None
    return Project(
        name=proj.get("name", proj_dir.name),
        type=ptype,
        description=proj.get("description", ""),
        root=proj_dir,
        tasks_dir=proj_dir / paths.get("tasks", "tasks"),
        checks_dir=proj_dir / paths.get("checks", "checks"),
        rubric_path=rubrics_path,
        extra_references_dir=proj_dir / paths.get("extra_references", "extra_references"),
        validation_mode=validation.get("mode", "skip"),
        # Harbor tasks share one common check set; non-Harbor projects only ever
        # run the checks written for them.
        include_common_checks=bool(checks.get("include_common", ptype == "harbor")),
        trajectory_analysis_path=trajectory_rubric_path,
        trajectory_analysis_prompt_path=trajectory_prompt,
        include_task_in_trajectory_analysis=bool(
            trajectory.get("include_task", True)
        ),
    )


def template_dir(project_type: str) -> Path:
    return PROJECTS_ROOT / project_type / f"{project_type}{TEMPLATE_SUFFIX}"


def create_project(
    name: str,
    project_type: str,
    description: str = "",
    validation_mode: str | None = None,
) -> Project:
    """Scaffold projects/<type>/<name>/ from the matching template."""
    validate_project_name(name)
    if project_type not in PROJECT_TYPES:
        raise ValueError(
            f"invalid project type: {project_type!r} (expected one of {PROJECT_TYPES})"
        )
    if validation_mode is None:
        validation_mode = "oracle_nop" if project_type == "harbor" else "skip"
    if validation_mode not in VALIDATION_MODES:
        raise ValueError(
            f"invalid validation mode: {validation_mode!r} (expected one of {VALIDATION_MODES})"
        )
    if project_exists(name):
        raise FileExistsError(f"project already exists: {name}")

    proj_dir = PROJECTS_ROOT / project_type / name
    if proj_dir.exists():
        raise FileExistsError(f"directory already exists: {proj_dir}")

    template_toml = template_dir(project_type) / "project.toml"
    if not template_toml.is_file():
        raise FileNotFoundError(f"project template missing: {template_toml}")

    proj_dir.mkdir(parents=True)
    try:
        for sub in ("tasks", "checks", "rubrics", "extra_references"):
            d = proj_dir / sub
            d.mkdir()
            (d / ".gitkeep").touch()
        rendered = (
            template_toml.read_text()
            .replace("{{name}}", name)
            .replace("{{type}}", project_type)
            .replace("{{description}}", description.replace('"', "'"))
            .replace("{{validation_mode}}", validation_mode)
        )
        (proj_dir / "project.toml").write_text(rendered)
    except Exception:
        shutil.rmtree(proj_dir, ignore_errors=True)
        raise

    return load_project(name)


def resolve_task(project: Project, task_id: str) -> Path:
    """Resolve a task identifier to a filesystem path.

    Harbor: tasks/<task_id>/ directory.
    Non-Harbor: tasks/<task_id>.json file or tasks/<task_id>/ directory.
    """
    candidate_dir = project.tasks_dir / task_id
    if candidate_dir.is_dir():
        return candidate_dir
    candidate_file = project.tasks_dir / f"{task_id}.json"
    if candidate_file.is_file():
        return candidate_file
    raise FileNotFoundError(
        f"task not found in project '{project.name}': {task_id} "
        f"(looked for {candidate_dir} and {candidate_file})"
    )


def list_tasks(project: Project) -> list[str]:
    """List task identifiers available in a project's tasks/ directory."""
    if not project.tasks_dir.is_dir():
        return []
    ids: set[str] = set()
    for entry in project.tasks_dir.iterdir():
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            ids.add(entry.name)
        elif entry.suffix == ".json":
            ids.add(entry.stem)
    return sorted(ids)
