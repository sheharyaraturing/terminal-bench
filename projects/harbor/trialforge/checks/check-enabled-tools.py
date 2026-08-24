#!/usr/bin/env python3
"""enabled_tools against the shipped tool inventory.

The harness filters client-side:  tools.filter(t => enabledTools.includes(t.name))
A misspelled name is a SILENT set intersection - the tool simply never reaches
the model, the agent underperforms for no visible reason, and nothing in Harbor,
the harness, or the sandbox says a word.
"""
from __future__ import annotations

from _lib import (declared_servers, enabled_tools, load_inventory, load_toml,
                  make_err, report, task_arg, tool_prefix)


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    inventory = load_inventory()
    if not inventory:
        err("ci/tool_inventory.txt: missing or empty. It is the offline copy of "
            "POST /list-tools for the pinned image and must be committed so this "
            "check needs no network.")

    task_cfg = load_toml(task / "task.toml", err)
    tools = enabled_tools(task_cfg)
    if tools is None:
        err(f"{task}/task.toml: [metadata].enabled_tools is required and must be a "
            "non-empty array of strings. Harbor itself ignores [metadata]; the wrapper "
            "reads this list and passes it to the harness as enabledTools. Without it "
            "the agent is handed the entire 210-tool surface.")
        return report("check-enabled-tools", task, errors, notes)

    # Duplicate entries are reported by check-mcp-config (which owns the
    # enabled_tools <-> declared-server cross-reference); not repeated here.

    if inventory:
        for t in tools:
            if t not in inventory:
                # Point at the double-prefix trap by name where we can.
                near = sorted(n for n in inventory if t in n or n.endswith("_" + t))
                hint = f" Did you mean: {near[:3]}?" if near else ""
                err(f"{task}/task.toml: enabled_tools entry {t!r} is not in the image's "
                    f"tool inventory.{hint}")

    servers = sorted({tool_prefix(t) for t in tools})
    notes.append(f"enabled_tools spans {len(servers)} server prefixes: {', '.join(servers)}")

    # Declared MCP servers are informational (the wrapper does not use
    # mcp_servers - tools come via enabledTools), but a task whose allowlist
    # names a server it never declares is almost certainly a copy-paste error
    # worth surfacing as a note, not a hard fail.
    declared = declared_servers(task_cfg)
    if declared:
        orphan = sorted(set(servers) - declared)
        if orphan:
            notes.append(f"enabled_tools references servers not declared in "
                         f"[[environment.mcp_servers]]: {orphan}")

    return report("check-enabled-tools", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
