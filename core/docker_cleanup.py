"""Tear down the Docker artifacts a harbor check leaves behind.

On a clean finish harbor removes its own compose project. When a run is killed
mid-flight — cancelled, timed out, or the server died — the container and its
compose network survive. Naming is predictable:

    container  check-<task>__<id>__env-main-1
    project    check-<task>__<id>__env
    network    check-<task>__<id>__env_default
"""
from __future__ import annotations

import subprocess

CHECK_PREFIX = "check-"
_CONTAINER_SUFFIX = "-main-1"


def _docker(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout
    )


def compose_project_of(container_name: str) -> str:
    """The compose project a harbor check container belongs to."""
    if container_name.endswith(_CONTAINER_SUFFIX):
        return container_name[: -len(_CONTAINER_SUFFIX)]
    return container_name


def remove_container(name: str) -> bool:
    return _docker("rm", "-f", name).returncode == 0


def remove_network(name: str) -> bool:
    return _docker("network", "rm", name).returncode == 0


def teardown_container(container_name: str) -> list[str]:
    """Remove one check container and the compose network it created."""
    removed: list[str] = []
    if remove_container(container_name):
        removed.append(f"container {container_name}")
    network = f"{compose_project_of(container_name)}_default"
    if remove_network(network):
        removed.append(f"network {network}")
    return removed


def list_leftovers() -> dict[str, list[dict]]:
    """Harbor check containers and networks that are no longer doing anything.

    Running containers are reported separately and never swept: one of them may
    belong to a review that is still in progress.
    """
    containers: list[dict] = []
    proc = _docker(
        "ps", "-a", "--filter", f"name={CHECK_PREFIX}", "--format", "{{.Names}}\t{{.Status}}"
    )
    for line in proc.stdout.splitlines():
        name, _, status = line.partition("\t")
        if not name:
            continue
        containers.append(
            {"name": name, "status": status, "running": status.startswith("Up")}
        )

    networks: list[dict] = []
    proc = _docker("network", "ls", "--format", "{{.Name}}")
    for name in proc.stdout.splitlines():
        if not name.startswith(CHECK_PREFIX):
            continue
        inspect = _docker("network", "inspect", name, "--format", "{{len .Containers}}")
        try:
            attached = int(inspect.stdout.strip() or "0")
        except ValueError:
            attached = 0
        networks.append({"name": name, "attached": attached})

    return {"containers": containers, "networks": networks}


def sweep_leftovers() -> dict[str, list[str]]:
    """Remove stopped check containers and unattached check networks.

    Anything still running is left alone — it may be an active review.
    """
    state = list_leftovers()
    removed: list[str] = []
    skipped: list[str] = []

    for container in state["containers"]:
        if container["running"]:
            skipped.append(f"container {container['name']} (still running)")
            continue
        removed.extend(teardown_container(container["name"]))

    for network in state["networks"]:
        if network["attached"] > 0:
            skipped.append(f"network {network['name']} ({network['attached']} attached)")
            continue
        if remove_network(network["name"]):
            removed.append(f"network {network['name']}")

    return {"removed": removed, "skipped": skipped}
