"""Housekeeping: inspect and clean up Docker artifacts left by reviews."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.docker_cleanup import list_leftovers, sweep_leftovers

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


@router.get("/docker")
def get_docker_state() -> dict:
    """Harbor check containers and networks currently on this machine."""
    try:
        state = list_leftovers()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"docker unavailable: {exc}") from exc
    state["reclaimable"] = sum(
        1 for c in state["containers"] if not c["running"]
    ) + sum(1 for n in state["networks"] if n["attached"] == 0)
    return state


@router.post("/docker/cleanup")
def post_docker_cleanup() -> dict:
    """Remove stopped check containers and unattached check networks.

    Anything still running is left alone: it may be an active review.
    """
    try:
        return sweep_leftovers()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"docker unavailable: {exc}") from exc
