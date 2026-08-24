#!/usr/bin/env python3
"""MCP server declarations: structural validity + enabled-tools coverage.

docs/ENVIRONMENT.md: Harbor does not gate tools — whatever a declared server
advertises, the agent sees. The vendored harness then filters client-side with
tools.filter(t => enabledTools.includes(t.name)). Two silent failures follow:

  1. An enabled tool whose server is NOT declared never reaches the model.
     The server isn't running, so the tool isn't in the list, and the filter
     is a no-op intersection. The task author thinks the tool is available; it
     isn't. check-enabled-tools does NOT catch this — it only checks names
     against the inventory, not against declared servers.
  2. A declared server with ZERO enabled tools runs but contributes nothing —
     wasted memory and boot time for a tool surface the model will never see.

This check also enforces the structural contract: each
[[environment.mcp_servers]] block must have name + transport, and either
(command + args) or url. Server names must be unique — a duplicate silently
shadows one entry in Harbor's server map.
"""
from __future__ import annotations

import sys

from _lib import (declared_servers, enabled_tools, load_toml, make_err,
                  report, task_arg, tool_prefix)


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    task_cfg = load_toml(task / "task.toml", err)
    env = task_cfg.get("environment") or {}
    servers = env.get("mcp_servers") or []

    # --- structural validation ---
    seen_names: set[str] = set()
    for i, s in enumerate(servers):
        if not isinstance(s, dict):
            err(f"{task}/task.toml: [[environment.mcp_servers]]#{i} is not a table")
            continue
        name = s.get("name")
        transport = s.get("transport")
        label = name or f"#{i}"
        if not name:
            err(f"{task}/task.toml: [[environment.mcp_servers]]#{i}: missing 'name'")
        if not transport:
            err(f"{task}/task.toml: [[environment.mcp_servers]]#{i} ({label}): "
                "missing 'transport'")
        has_cmd = isinstance(s.get("command"), str)
        has_url = isinstance(s.get("url"), str)
        if not has_cmd and not has_url:
            err(f"{task}/task.toml: [[environment.mcp_servers]]#{i} ({label}): "
                "must have 'command' (stdio) or 'url' (sse/http)")
        if name and name in seen_names:
            err(f"{task}/task.toml: duplicate server name {name!r} — the second "
                "declaration silently shadows the first in Harbor's server map")
        if name:
            seen_names.add(name)

    # --- cross-reference enabled_tools against declared servers ---
    tools = enabled_tools(task_cfg)
    if tools is None:
        # check-enabled-tools reports the missing/malformed list.
        return report("check-mcp-config", task, errors,
                      ["enabled_tools missing; see check-enabled-tools"])

    # Duplicate enabled_tools entries are dead weight from a copy-paste error.
    seen: set[str] = set()
    dupes: set[str] = set()
    for t in tools:
        if t in seen:
            dupes.add(t)
        seen.add(t)
    if dupes:
        err(f"{task}/task.toml: duplicate enabled_tools entries: "
            f"{', '.join(sorted(dupes))}")

    declared = declared_servers(task_cfg)
    tool_servers = {tool_prefix(t) for t in tools}

    # Every enabled tool must come from a declared server.
    undeclared = sorted(tool_servers - declared)
    if undeclared:
        orphan_tools = sorted(t for t in tools if tool_prefix(t) in undeclared)
        err(f"{task}/task.toml: {len(orphan_tools)} enabled tool(s) reference "
            f"undeclared server(s): {', '.join(undeclared)}. These servers are not "
            "in [[environment.mcp_servers]], so their tools never reach the model — "
            f"silent no-ops: {', '.join(orphan_tools)}")

    # Every declared server must have at least one enabled tool.
    dead = sorted(declared - tool_servers)
    if dead:
        err(f"{task}/task.toml: declared server(s) with no enabled tools: "
            f"{', '.join(dead)}. The server runs but contributes nothing to the "
            "model's tool surface — wasted memory and boot time.")

    return report("check-mcp-config", task, errors, notes)


if __name__ == "__main__":
    sys.exit(main())
