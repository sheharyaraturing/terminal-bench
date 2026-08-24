#!/usr/bin/env python3
"""MCP server declarations: exactly one `gw` SSE gateway, structurally valid.

Toolathon tasks expose tools through a single gateway server (`gw`) over SSE;
the per-server allowlist lives in [environment.env].MCP_SERVERS, not here. This
check enforces the structural contract:
  - exactly one [[environment.mcp_servers]] block
  - it is named `gw`, transport `sse`, with a url and no command (never stdio)
  - server names are unique

A stdio server, a second gateway, or a missing url all break the tool surface
in ways that surface only as a health-check timeout.
"""
from __future__ import annotations

import sys

from _lib import GATEWAY_SERVER, load_toml, make_err, report, task_arg


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    task_cfg = load_toml(task / "task.toml", err)
    env = task_cfg.get("environment") or {}
    servers = env.get("mcp_servers") or []

    if not servers:
        err(f"{task}/task.toml: no [[environment.mcp_servers]] block. Toolathon tasks "
            f"declare a single {GATEWAY_SERVER!r} SSE gateway server.")
        return report("check-mcp-config", task, errors, notes)

    if len(servers) > 1:
        err(f"{task}/task.toml: {len(servers)} [[environment.mcp_servers]] blocks; "
            f"toolathon tasks declare exactly one {GATEWAY_SERVER!r} gateway. Extra "
            "servers belong in [environment.env].MCP_SERVERS, not as MCP blocks.")

    seen: set[str] = set()
    for i, s in enumerate(servers):
        if not isinstance(s, dict):
            err(f"{task}/task.toml: [[environment.mcp_servers]]#{i} is not a table")
            continue
        name = s.get("name")
        transport = s.get("transport")
        label = name or f"#{i}"

        if not name:
            err(f"{task}/task.toml: [[environment.mcp_servers]]#{i}: missing 'name'")
        elif name in seen:
            err(f"{task}/task.toml: duplicate server name {name!r} - the second "
                "declaration silently shadows the first in Harbor's server map")
        if name:
            seen.add(name)

        if name and name != GATEWAY_SERVER:
            notes.append(f"server {name!r} is not the standard {GATEWAY_SERVER!r} "
                         "gateway - confirm this is deliberate.")

        if not transport:
            err(f"{task}/task.toml: [[environment.mcp_servers]]#{i} ({label}): "
                "missing 'transport'")
        elif transport != "sse":
            err(f"{task}/task.toml: server {label!r} transport = {transport!r}, expected "
                "'sse'. Toolathon's gateway is SSE; stdio servers are not used.")

        # SSE servers need a url, and must NOT carry a stdio command.
        if isinstance(s.get("command"), str):
            err(f"{task}/task.toml: server {label!r} sets 'command' (stdio). Toolathon "
                "uses a url-based SSE gateway; remove the command.")
        if not isinstance(s.get("url"), str):
            err(f"{task}/task.toml: server {label!r} must set 'url' (the SSE endpoint).")

    return report("check-mcp-config", task, errors, notes)


if __name__ == "__main__":
    sys.exit(main())
