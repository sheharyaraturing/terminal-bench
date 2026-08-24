"""Review execution and run inspection."""
from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from core.registry import load_project

from . import jobs, store
from .models import ExecuteRequest, LogChunk, RunAccepted

router = APIRouter(prefix="/api", tags=["runs"])

# Trajectories zips are whole Harbor jobs trees (tens of MB), so they get a
# larger budget than a single uploaded file.
TRAJECTORY_MAX_BYTES = 500 * 1024 * 1024


@router.post("/execute", response_model=RunAccepted, status_code=202)
def post_execute(req: ExecuteRequest) -> RunAccepted:
    """Queue a review. Returns immediately; poll /api/runs/{run_id} for state."""
    if req.is_gcs:
        raise HTTPException(
            status_code=501,
            detail=(
                "GCS task sources are not implemented yet. Upload the task via "
                "POST /api/projects/{name}/tasks and pass data.task_id instead."
            ),
        )
    if not req.data.task_id:
        raise HTTPException(status_code=400, detail="data.task_id is required when is_gcs is false")

    try:
        status = jobs.submit_run(
            project_name=req.project_name,
            task_id=req.data.task_id,
            project_id=req.project_id,
            reviewer_email=req.reviewer_email,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RunAccepted(
        run_id=status["run_id"],
        state=status["state"],
        project=status["project"],
        task_id=status["task_id"],
    )


@router.get("/projects/{name}/jobs")
def get_project_jobs(name: str) -> dict:
    """The folder/run tree currently in the project's jobs dir (rerun view)."""
    try:
        project = load_project(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return store.list_project_jobs(project)


@router.post("/projects/{name}/jobs", status_code=200)
async def post_project_jobs(name: str, file: UploadFile = File(...)) -> dict:
    """Extract an uploaded trajectories zip into the project's jobs dir and
    return the resulting folder/run tree plus the folders that were added."""
    try:
        project = load_project(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > TRAJECTORY_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"trajectories zip is over the {TRAJECTORY_MAX_BYTES}-byte limit",
            )
        chunks.append(chunk)
    return store.extract_trajectory_zip(project, b"".join(chunks))


@router.post("/execute-trajectory", response_model=RunAccepted, status_code=202)
def post_execute_trajectory(
    project_name: str = Form(...),
    task_id: str | None = Form(None),
    reviewer_email: str | None = Form(None),
    selected: str | None = Form(None),
) -> RunAccepted:
    """Queue a trajectory-analysis run over the project's jobs dir.

    ``selected`` is an optional JSON array of trial-directory paths (relative to
    the project jobs dir) to analyze; omit it to analyze every trial. Returns
    immediately; poll /api/runs/{run_id} for state.
    """
    selected_paths: list[str] | None = None
    if selected:
        try:
            parsed = json.loads(selected)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"invalid selected JSON: {exc}") from exc
        if not isinstance(parsed, list) or not all(isinstance(p, str) for p in parsed):
            raise HTTPException(status_code=400, detail="selected must be a JSON array of paths")
        selected_paths = parsed or None

    try:
        status = jobs.submit_trajectory_run(
            project_name=project_name,
            task_id=task_id,
            selected=selected_paths,
            reviewer_email=reviewer_email,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RunAccepted(
        run_id=status["run_id"],
        state=status["state"],
        project=status["project"],
        task_id=status["task_id"],
    )


@router.get("/runs")
def get_runs(
    limit: int = Query(50, ge=1, le=500), project: str | None = None
) -> list[dict]:
    return store.list_runs(limit=limit, project=project)


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    try:
        return store.read_status(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/report")
def get_run_report(run_id: str) -> dict:
    try:
        return store.read_report(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/cancel")
def post_cancel_run(run_id: str) -> dict:
    """Stop a queued or running review, tearing down its containers."""
    try:
        status = store.read_status(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if status["state"] in store.TERMINAL_STATES:
        raise HTTPException(
            status_code=409,
            detail=f"run already finished with state '{status['state']}'",
        )
    if not jobs.cancel_run(run_id):
        # Active per status.json but no live control: the server restarted
        # while it was running, so nothing is left to stop.
        store.update_status(
            run_id,
            state="cancelled",
            passed=False,
            error="cancelled (no live process; server likely restarted)",
            finished_at=store.now_iso(),
        )

    # A run can finish while the request is in flight; report what actually
    # happened rather than assuming the cancel won the race.
    final = store.read_status(run_id)
    return {"run_id": run_id, "state": final["state"], "requested": "cancel"}


@router.get("/runs/{run_id}/log", response_model=LogChunk)
def get_run_log(run_id: str, offset: int = Query(0, ge=0)) -> LogChunk:
    try:
        status = store.read_status(run_id)
        text, new_offset = store.read_log(run_id, offset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LogChunk(run_id=run_id, offset=new_offset, text=text, state=status["state"])
