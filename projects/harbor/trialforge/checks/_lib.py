"""Shared helpers for trialforge deterministic task checks.

Every check is a standalone script invoked as:

    python3 checks/check-<name>.py tasks/<slug>

Contract (matches terminal-bench core/deterministic.py):
  - exit 0 = pass, non-zero = fail
  - print "FAIL <path>: <reason>" lines for failures, "NOTE ..." for advisory
  - collect every failure before exiting; never fail-fast on the first

Tunables come from the environment so CI and local runs use the same values.
"""
from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path

# This file lives at projects/harbor/trialforge/checks/_lib.py.
# Project root = checks/..   (the trialforge project directory).
CHECKS_DIR = Path(__file__).resolve().parent
ROOT = CHECKS_DIR.parent
# The tool inventory is committed alongside the checks (not under ci/ — this
# is a project-local copy, not the standalone-repo layout the checks were
# originally written for).
INVENTORY = CHECKS_DIR / "tool_inventory.txt"

IMAGE_PREFIX = os.environ.get(
    "IMAGE_PREFIX",
    "us-central1-docker.pkg.dev/turing-delivery-rl-gym/daytona/turing-mcpatlas:",
)
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "openrouter/openai/gpt-5.6-luna")
MIN_CLAIMS = int(os.environ.get("MIN_CLAIMS", "8"))
MAX_CLAIMS = int(os.environ.get("MAX_CLAIMS", "15"))
MIN_EXPOSED = int(os.environ.get("MIN_EXPOSED", "18"))
MAX_EXPOSED = int(os.environ.get("MAX_EXPOSED", "30"))
MIN_TOOL_CALLS = int(os.environ.get("MIN_TOOL_CALLS", "40"))
MAX_TOOL_CALLS = int(os.environ.get("MAX_TOOL_CALLS", "70"))
CLAIMS_TOLERANCE = int(os.environ.get("CLAIMS_TOLERANCE", "4"))
DOMAINS = {"software-engineering", "research-science"}


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


def load_inventory() -> set[str]:
    """The image's full tool surface (names only), committed for offline CI."""
    tools: set[str] = set()
    if not INVENTORY.is_file():
        return tools
    for line in read_text(INVENTORY).splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            tools.add(line)
    return tools


def tool_prefix(tool: str) -> str:
    """Server prefix of a tool name. Names are already namespaced {server}_{tool};
    some servers contain hyphens (ddg-search_search), so split on the LAST
    underscore that leaves a known server prefix is overkill - the convention in
    this repo (verify_allowlists.py, task-pr.yml) is split('_', 1)[0]."""
    return tool.split("_", 1)[0]


def task_config(task: Path, err) -> dict:
    return load_toml(task / "task.toml", err)


def reward_config(task: Path, err) -> dict:
    return load_toml(task / "tests" / "reward.toml", err)


def enabled_tools(task_cfg: dict):
    meta = task_cfg.get("metadata") or {}
    tools = meta.get("enabled_tools")
    if isinstance(tools, list) and all(isinstance(t, str) for t in tools):
        return tools
    return None


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
