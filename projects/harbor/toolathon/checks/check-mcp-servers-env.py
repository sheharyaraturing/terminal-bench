#!/usr/bin/env python3
"""[environment.env].MCP_SERVERS: the toolathon tool allowlist.

The gateway reads MCP_SERVERS and exposes each named server's tools. A typo is a
SILENT no-op - the gateway simply never exposes that server, the agent
underperforms for no visible reason, and nothing in Harbor or the runtime says a
word. This is toolathon's analogue of trialforge's check-enabled-tools.

Enforces:
  - MCP_SERVERS parses to a non-empty list
  - every name is a real server in extra_references/tool-list.json
  - no duplicates
  - the base servers (filesystem, terminal) are always present
  - LOCAL_TOOLS names only known local tools (claim_done)
"""
from __future__ import annotations

import sys

from _lib import (BASE_SERVERS, KNOWN_LOCAL_TOOLS, env_block, known_servers,
                  load_toml, make_err, mcp_servers_env, report, task_arg)


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    task_cfg = load_toml(task / "task.toml", err)
    servers = mcp_servers_env(task_cfg)
    if servers is None:
        err(f"{task}/task.toml: [environment.env].MCP_SERVERS is required and must be a "
            "comma-separated string of server names. check-task-toml also enforces this.")
        return report("check-mcp-servers-env", task, errors, notes)

    if not servers:
        err(f"{task}/task.toml: [environment.env].MCP_SERVERS is empty - the gateway "
            "would expose no tools.")
        return report("check-mcp-servers-env", task, errors, notes)

    known = known_servers()
    if not known:
        err("extra_references/tool-list.json: missing or has no 'server' fields. It is "
            "the offline copy of the image's tool surface and must be committed so this "
            "check needs no network.")

    # Duplicates are dead weight from a copy-paste error.
    seen: set[str] = set()
    for s in servers:
        if s in seen:
            err(f"{task}/task.toml: duplicate MCP_SERVERS entry {s!r}.")
        seen.add(s)

    # Every named server must be real.
    if known:
        for s in servers:
            if s not in known:
                near = sorted(n for n in known if s.lower() in n.lower() or n.lower() in s.lower())
                hint = f" Did you mean: {near[:3]}?" if near else ""
                err(f"{task}/task.toml: MCP_SERVERS entry {s!r} is not a known server.{hint}")

    # The base servers must always be present.
    missing_base = sorted(BASE_SERVERS - set(servers))
    if missing_base:
        err(f"{task}/task.toml: MCP_SERVERS is missing base server(s) "
            f"{', '.join(missing_base)} - every toolathon task needs filesystem + terminal.")

    # LOCAL_TOOLS names only known local tools.
    local_raw = env_block(task_cfg, "environment").get("LOCAL_TOOLS")
    if isinstance(local_raw, str) and local_raw.strip():
        for t in [x.strip() for x in local_raw.split(",") if x.strip()]:
            if t not in KNOWN_LOCAL_TOOLS:
                err(f"{task}/task.toml: LOCAL_TOOLS entry {t!r} is not a known local tool "
                    f"(known: {sorted(KNOWN_LOCAL_TOOLS)}).")

    notes.append(f"MCP_SERVERS exposes {len(servers)} server(s): {', '.join(servers)}")
    return report("check-mcp-servers-env", task, errors, notes)


if __name__ == "__main__":
    sys.exit(main())
