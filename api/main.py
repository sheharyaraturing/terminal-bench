"""FastAPI application for the multi-project autoreviewer.

Run with:  ./run_api.sh      (or: uvicorn api.main:app --reload --port 8000)
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.registry import REPO_ROOT

from . import routes_maintenance, routes_projects, routes_runs, routes_tasks

UI_DIR = REPO_ROOT / "ui"

app = FastAPI(
    title="Autoreviewer API",
    description="Project setup (delivery manager) and task review (trainer) for the autoreviewer pipeline.",
    version="0.1.0",
)

# Local PoC: the UI is served from the same origin, but keep CORS open so the
# API can also be driven from a separately-hosted front end during testing.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_projects.router)
app.include_router(routes_tasks.router)
app.include_router(routes_runs.router)
app.include_router(routes_maintenance.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "repo_root": str(REPO_ROOT)}


def _load_dotenv(path: Path) -> None:
    """Same minimal .env loader execute.py uses, so the rubric leg gets its key."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(REPO_ROOT / ".env")


@app.on_event("startup")
def _reap_orphaned_runs() -> None:
    """Close out runs the previous process was executing when it stopped.

    Their worker threads died with it, so nothing will ever finish them; left
    alone they sit at "running" forever and their containers leak.
    """
    from . import store

    for status in store.list_runs(limit=500):
        if status.get("state") in store.TERMINAL_STATES:
            continue
        run_id = status["run_id"]
        for leg, detail in status.get("legs", {}).items():
            if detail.get("state") in ("running", "pending"):
                store.set_leg(run_id, leg, "interrupted", detail.get("summary", ""))
        store.append_log(run_id, "run interrupted: the API process stopped while it was executing")
        store.update_status(
            run_id,
            state="error",
            passed=False,
            error="interrupted by an API restart",
            finished_at=store.now_iso(),
        )

if UI_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
