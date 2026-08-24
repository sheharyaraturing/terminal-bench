#!/usr/bin/env python3
"""[environment.healthcheck]: the gateway boot probe must be well-formed.

The healthcheck runs runtime/setup.sh, which writes task_config.json from
MCP_SERVERS/LOCAL_TOOLS and starts the container_tool_gateway. A malformed
healthcheck is a silent boot failure that surfaces only as a health-check
timeout that looks like a network fault. All 16 tasks carry the identical block.
"""
from __future__ import annotations

import sys

from _lib import load_toml, make_err, report, task_arg


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    task_cfg = load_toml(task / "task.toml", err)
    hc = (task_cfg.get("environment") or {}).get("healthcheck")

    if not isinstance(hc, dict):
        err(f"{task}/task.toml: [environment.healthcheck] is missing. The gateway boot "
            "probe (runtime/setup.sh) must run before the agent or the tool surface "
            "never comes up.")
        return report("check-healthcheck", task, errors, notes)

    command = hc.get("command")
    if not (isinstance(command, str) and command.strip()):
        err(f"{task}/task.toml: [environment.healthcheck].command is required and must "
            "be a non-empty string (it runs runtime/setup.sh).")

    for key in ("timeout_sec", "interval_sec", "retries"):
        v = hc.get(key)
        if not isinstance(v, (int, float)) or v <= 0:
            err(f"{task}/task.toml: [environment.healthcheck].{key} = {v!r}, expected a "
                "positive number.")

    start_period = hc.get("start_period_sec")
    if not isinstance(start_period, (int, float)) or start_period < 0:
        err(f"{task}/task.toml: [environment.healthcheck].start_period_sec = "
            f"{start_period!r}, expected a number >= 0.")

    return report("check-healthcheck", task, errors, notes)


if __name__ == "__main__":
    sys.exit(main())
