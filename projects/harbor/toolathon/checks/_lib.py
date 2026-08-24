"""Shared helpers for toolathon deterministic task checks.

Every check is a standalone script invoked as:

    python3 checks/check-<name>.py tasks/<slug>

Contract (matches terminal-bench core/deterministic.py):
  - exit 0 = pass, non-zero = fail
  - print "FAIL <path>: <reason>" lines for failures, "NOTE ..." for advisory
  - collect every failure before exiting; never fail-fast on the first

Toolathon tasks are Toolathlon-derived: the tool surface is selected via the
[environment.env].MCP_SERVERS comma-list (server names, not per-tool), graded by
rewardkit [[reward]] blocks + per-dimension tests/<dir>/check.py, and built on
the task-image base. There is no enabled_tools / [judge] / [[criterion]].
"""
from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path

# This file lives at projects/harbor/toolathon/checks/_lib.py.
# Project root = checks/..   (the toolathon project directory).
CHECKS_DIR = Path(__file__).resolve().parent
ROOT = CHECKS_DIR.parent
# The tool inventory is the project's extra_references/tool-list.json: a flat
# array of tool objects, each with a "server" field. Committed for offline CI.
TOOL_LIST = ROOT / "extra_references" / "tool-list.json"

IMAGE_PREFIX = os.environ.get(
    "IMAGE_PREFIX",
    "us-central1-docker.pkg.dev/turing-delivery-rl-gym/daytona/task-image:",
)
# The single gateway server every toolathon task declares.
GATEWAY_SERVER = "gw"
GATEWAY_PORT = "8765"
# Local (non-MCP) tools the runtime always exposes.
KNOWN_LOCAL_TOOLS = {"claim_done"}
# Servers that must always be present in MCP_SERVERS (the base surface).
BASE_SERVERS = {"filesystem", "terminal"}


def task_arg() -> Path:
    """The single positional argument: the task directory."""
    if len(sys.argv) < 2:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <task-dir>")
    task = Path(sys.argv[1])
    if not task.is_dir():
        sys.exit(f"FATAL: {task} is not a directory")
    return task


def load_toml(path: Path, err) -> dict:
    """Parse TOML with the same parser Harbor/rewardkit use. Errors go to err."""
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        err(f"{path}: missing")
    except tomllib.TOMLDecodeError as e:
        err(f"{path}: not valid TOML - {e}")
    return {}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def load_tool_list() -> list[dict]:
    """The flat tool inventory from extra_references/tool-list.json."""
    if not TOOL_LIST.is_file():
        return []
    try:
        data = json.loads(TOOL_LIST.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def known_servers() -> set[str]:
    """The set of valid MCP server names (from tool-list.json's server field)."""
    return {str(t.get("server")) for t in load_tool_list() if t.get("server")}


def known_tools() -> set[str]:
    """Bare tool names (e.g. create_directory) from tool-list.json."""
    return {str(t.get("name")) for t in load_tool_list() if t.get("name")}


def prefixed_tools() -> set[str]:
    """Runtime tool names: {server}_{tool} (e.g. filesystem_create_directory)."""
    out: set[str] = set()
    for t in load_tool_list():
        name, server = t.get("name"), t.get("server")
        if name and server:
            out.add(f"{server}_{name}")
    return out


def task_config(task: Path, err) -> dict:
    return load_toml(task / "task.toml", err)


def reward_config(task: Path, err) -> dict:
    return load_toml(task / "tests" / "reward.toml", err)


def env_block(task_cfg: dict, section: str) -> dict:
    """task_cfg[section]['env'] as a dict, or {} if absent/malformed."""
    env = (task_cfg.get(section) or {}).get("env")
    return env if isinstance(env, dict) else {}


def mcp_servers_env(task_cfg: dict) -> list[str] | None:
    """[environment.env].MCP_SERVERS parsed into a list of server names.

    Returns None if the key is missing or not a string (the caller reports the
    missing-key failure)."""
    raw = env_block(task_cfg, "environment").get("MCP_SERVERS")
    if not isinstance(raw, str):
        return None
    return [s.strip() for s in raw.split(",") if s.strip()]


def declared_servers(task_cfg: dict) -> set[str]:
    env = task_cfg.get("environment") or {}
    servers = env.get("mcp_servers") or []
    return {s.get("name") for s in servers if isinstance(s, dict) and s.get("name")}


def make_err(errors: list[str]):
    def err(msg: str) -> None:
        errors.append(msg)

    return err


def report(name: str, task: Path, errors: list[str], notes: list[str]) -> int:
    """Print a uniform per-check report and return the process exit code."""
    for n in notes:
        print(f"NOTE {task}: {n}")
    if errors:
        for e in errors:
            print(f"FAIL {e}")
        print(f"{name}: {len(errors)} problem(s)")
        return 1
    print(f"{name}: OK ({task})")
    return 0


# core/deterministic.py discovers project checks with require_prefix=False, so
# it picks up every .py in this dir — including this library module. Running
# it directly does nothing; exit 0 so it shows as a harmless no-op rather than
# a confusing phantom failure.
if __name__ == "__main__":
    sys.exit(0)
