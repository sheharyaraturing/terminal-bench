#!/usr/bin/env python3
"""Allowlist size band.

docs/TOOL_ALLOWLISTS.md: MCP-Atlas exposes ~15 tools/task; trialforge holds
18-30 so the distractor ratio stays near the benchmark's while covering 40-70
calls. Previously only enforced by ci/verify_allowlists.py, not by CI.
"""
from __future__ import annotations

from _lib import (MAX_EXPOSED, MIN_EXPOSED, enabled_tools, load_toml, make_err,
                  report, task_arg)


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    err = make_err(errors)

    task_cfg = load_toml(task / "task.toml", err)
    tools = enabled_tools(task_cfg)
    if tools is None:
        # check-enabled-tools already reports the missing/malformed list.
        return report("check-allowlist-budget", task, errors,
                      ["enabled_tools missing; see check-enabled-tools"])

    if not MIN_EXPOSED <= len(tools) <= MAX_EXPOSED:
        err(f"{task}/task.toml: {len(tools)} tools exposed, outside the "
            f"{MIN_EXPOSED}-{MAX_EXPOSED} band (docs/TOOL_ALLOWLISTS.md). Too few and "
            "tool selection is trivial; too many and the surface is noise, not signal.")

    return report("check-allowlist-budget", task, errors, [])


if __name__ == "__main__":
    raise SystemExit(main())
