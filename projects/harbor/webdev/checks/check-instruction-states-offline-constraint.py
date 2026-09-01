#!/usr/bin/env python3
"""NOTE-only: an offline task should say so in the prompt.

When the agent phase runs with no network, the harness enforces it either way —
but an agent that was never told will reach for `npm install`, block, retry, and
burn its budget before working out that the registry is unreachable. That is a
fairness cost paid entirely by submissions that behave normally.

Never a failure: short static-page prompts legitimately omit it, and whether
the omission is unfair in a given task is a rubric judgment.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

MENTIONS_CONSTRAINT = re.compile(
    r"\binstall\b|\bnetwork\b|\bCDN\b|\boffline\b|external asset|"
    r"already (?:available|installed|provided)|no internet|without internet",
    re.IGNORECASE)


def task_arg() -> Path:
    if len(sys.argv) < 2:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <task-dir>")
    task = Path(sys.argv[1])
    if not task.is_dir():
        sys.exit(f"FATAL: {task} is not a directory")
    return task


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def main() -> int:
    task = task_arg()
    try:
        with (task / "task.toml").open("rb") as fh:
            cfg = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        cfg = {}

    network = (cfg.get("environment") or {}).get("network_mode")
    if network not in ("no-network", "none"):
        print(f"NOTE {task}: agent network_mode = {network!r}; no offline "
              "constraint to state.")
    elif not MENTIONS_CONSTRAINT.search(read_text(task / "instruction.md")):
        print(f"NOTE {task}: the agent phase runs with network_mode = {network!r}, "
              "but instruction.md never mentions installing, the network, or "
              "dependencies being already available. The harness enforces it "
              "regardless — but an agent that was not told will try `npm install`, "
              "block, and lose budget it should have spent building.")

    print(f"check-instruction-states-offline-constraint: OK ({task})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
