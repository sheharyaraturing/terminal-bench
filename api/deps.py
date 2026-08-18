"""Shared helpers for the API routers."""
from __future__ import annotations

import tomllib
from pathlib import Path

from fastapi import HTTPException

from core.registry import Project, load_project, validate_project_name
from api.files import UploadError


def get_project(name: str) -> Project:
    """Resolve a project name from the URL, or raise the right HTTP error."""
    try:
        validate_project_name(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return load_project(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def rubric_criteria(rubric_path: Path) -> list[str]:
    """Best-effort list of [[criteria]] names, for showing a rubric summary."""
    if not rubric_path.is_file():
        return []
    try:
        with rubric_path.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return []
    return [
        str(c.get("name", "(unnamed)"))
        for c in data.get("criteria", [])
        if isinstance(c, dict)
    ]


def listdir_names(path: Path) -> list[str]:
    if not path.is_dir():
        return []
    return sorted(p.name for p in path.iterdir() if p.is_file() and not p.name.startswith("."))
