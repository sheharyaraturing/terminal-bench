#!/usr/bin/env python3
"""Dangerous / degenerate allowlist shapes.

- sqlite_delete_records is banned outright: it can destroy the ground truth
  mid-rollout and make a bad rollout unrepeatable (docs/TOOL_ALLOWLISTS.md).
- Never expose a server's ENTIRE tool set (>2 tools): a dumped server is noise,
  not a distractor.
"""
from __future__ import annotations

from collections import Counter

from _lib import (enabled_tools, load_inventory, load_toml, make_err, report,
                  task_arg, tool_prefix)

BANNED = {"sqlite_delete_records"}


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    err = make_err(errors)

    task_cfg = load_toml(task / "task.toml", err)
    tools = enabled_tools(task_cfg)
    if tools is None:
        return report("check-no-dangerous-tools", task, errors,
                      ["enabled_tools missing; see check-enabled-tools"])

    for t in tools:
        if t in BANNED:
            err(f"{task}/task.toml: {t!r} must never be exposed - it can destroy the "
                "ground truth mid-rollout and make a bad rollout unrepeatable "
                "(docs/TOOL_ALLOWLISTS.md).")

    inventory = load_inventory()
    if inventory:
        total_per_server = Counter(tool_prefix(t) for t in inventory)
        exposed_per_server = Counter(tool_prefix(t) for t in tools)
        for server, n in sorted(exposed_per_server.items()):
            total = total_per_server.get(server, 0)
            if total > 2 and n == total:
                err(f"{task}/task.toml: exposes all {n} tools of server {server!r}. "
                    "Take 1-3 from each server; a dumped server is noise, not a distractor.")

    return report("check-no-dangerous-tools", task, errors, [])


if __name__ == "__main__":
    raise SystemExit(main())
