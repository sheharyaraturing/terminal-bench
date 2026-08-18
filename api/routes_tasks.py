"""Trainer flow: upload and list tasks for an existing project."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from core.registry import list_tasks

from . import files
from .deps import bad_request, get_project

router = APIRouter(prefix="/api/projects", tags=["tasks"])


@router.get("/{name}/tasks")
def get_tasks(name: str) -> dict:
    project = get_project(name)
    return {"project": project.name, "type": project.type, "tasks": list_tasks(project)}


@router.post("/{name}/tasks", status_code=201)
async def post_task(
    name: str,
    file: UploadFile = File(...),
    task_id: str | None = Form(None),
) -> dict:
    """Upload a task.

    `.zip` is extracted into tasks/<task_id>/ (a single wrapping directory in
    the archive is unwrapped, so zipping a task folder does the right thing).
    `.json` lands as tasks/<task_id>.json for non-Harbor projects.
    """
    project = get_project(name)
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in (".zip", ".json"):
        raise HTTPException(
            status_code=400, detail=f"unsupported task upload: {filename!r} (use .zip or .json)"
        )

    # Default the task id to the uploaded filename's stem.
    raw_id = task_id or Path(filename.replace("\\", "/")).stem
    try:
        tid = files.safe_task_id(raw_id)
    except files.UploadError as exc:
        raise bad_request(exc) from exc

    project.tasks_dir.mkdir(parents=True, exist_ok=True)
    data = await file.read()

    if suffix == ".json":
        try:
            json.loads(data.decode())
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc
        dest = project.tasks_dir / f"{tid}.json"
        if dest.exists():
            raise HTTPException(status_code=409, detail=f"task already exists: {tid}")
        try:
            files.write_upload(project.tasks_dir, f"{tid}.json", data, (".json",))
        except files.UploadError as exc:
            raise bad_request(exc) from exc
        return {"task_id": tid, "path": str(dest), "kind": "json"}

    dest_dir = project.tasks_dir / tid
    if dest_dir.exists():
        raise HTTPException(status_code=409, detail=f"task already exists: {tid}")
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "upload.zip"
        zip_path.write_bytes(data)
        try:
            files.extract_zip_safely(zip_path, dest_dir)
        except files.UploadError as exc:
            raise bad_request(exc) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"could not read archive: {exc}") from exc
    entries = sorted(p.name for p in dest_dir.iterdir())
    return {"task_id": tid, "path": str(dest_dir), "kind": "dir", "contents": entries}


@router.delete("/{name}/tasks/{task_id}")
def delete_task(name: str, task_id: str) -> dict:
    project = get_project(name)
    try:
        tid = files.safe_task_id(task_id)
    except files.UploadError as exc:
        raise bad_request(exc) from exc
    as_dir = project.tasks_dir / tid
    as_file = project.tasks_dir / f"{tid}.json"
    if as_dir.is_dir():
        shutil.rmtree(as_dir)
    elif as_file.is_file():
        as_file.unlink()
    else:
        raise HTTPException(status_code=404, detail=f"task not found: {tid}")
    return {"deleted": tid}
