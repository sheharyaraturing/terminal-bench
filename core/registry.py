"""Project registry: discover projects and resolve task paths."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECTS_ROOT = REPO_ROOT / "projects"


@dataclass(frozen=True)
class Project:
    name: str
    type: str  # "harbor" | "non-harbor"
    root: Path
    tasks_dir: Path
    checks_dir: Path
    rubric_path: Path
    extra_references_dir: Path
    validation_mode: str  # "oracle_nop" | "skip"


def _load_toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def list_projects() -> list[Project]:
    """Discover all projects under projects/<type>/<name>/project.toml."""
    projects: list[Project] = []
    if not PROJECTS_ROOT.is_dir():
        return projects
    for type_dir in sorted(PROJECTS_ROOT.iterdir()):
        if not type_dir.is_dir():
            continue
        for proj_dir in sorted(type_dir.iterdir()):
            cfg = proj_dir / "project.toml"
            if cfg.is_file():
                projects.append(load_project(proj_dir.name))
    return projects


def load_project(name: str) -> Project:
    """Load a project by name, searching projects/*/<name>/project.toml."""
    for type_dir in sorted(PROJECTS_ROOT.iterdir()):
        if not type_dir.is_dir():
            continue
        proj_dir = type_dir / name
        cfg = proj_dir / "project.toml"
        if cfg.is_file():
            data = _load_toml(cfg)
            proj = data.get("project", {})
            paths = data.get("paths", {})
            validation = data.get("validation", {})
            return Project(
                name=proj.get("name", name),
                type=proj.get("type", type_dir.name),
                root=proj_dir,
                tasks_dir=proj_dir / paths.get("tasks", "tasks"),
                checks_dir=proj_dir / paths.get("checks", "checks"),
                rubric_path=proj_dir / paths.get("rubrics", "rubrics/rubrics.toml"),
                extra_references_dir=proj_dir / paths.get("extra_references", "extra_references"),
                validation_mode=validation.get("mode", "skip"),
            )
    raise FileNotFoundError(f"project not found: {name}")


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
