#!/usr/bin/env python3
"""instruction.md must read as a natural persona request, not a grader spec.

The prompt is written in a persona's voice; it must not leak the machinery that
scores it. This check bans:
  - tool IDs (bare and {server}_-prefixed) from the image's tool inventory
  - MCP server names (incl. the gateway server `gw`)
  - the env keys that wire the tool surface (MCP_SERVERS / LOCAL_TOOLS / GATEWAY_PORT)
  - grader fourth-wall terms (rewardkit, judge, criterion, check.py, reward.toml)

A real instruction says "the delegation matrix" or "the reconciliation procedure",
never "use excel_write_data_to_excel" or "the rewardkit judge will check ...".
"""
from __future__ import annotations

import re
import sys

from _lib import (GATEWAY_SERVER, known_servers, known_tools, make_err,
                  prefixed_tools, read_text, report, task_arg)

# Grader / harness terms that must never appear in a persona instruction.
GRADER_TERMS = [
    "rewardkit", "reward.toml", "judge", "criterion", "check.py",
    "final_answer", "oracle", "trajectory", "verifier", "harbor",
]
# Env keys that wire the tool surface.
ENV_KEYS = ["MCP_SERVERS", "LOCAL_TOOLS", "GATEWAY_PORT", "TASK_ID"]


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    instr = task / "instruction.md"
    text = read_text(instr)
    if not text.strip():
        return report("check-instruction-hygiene", task, errors,
                      ["no instruction.md; see check-required-files"])
    lower = text.lower()

    # Grader fourth-wall terms (word-boundary, case-insensitive).
    for term in GRADER_TERMS:
        if re.search(rf"\b{re.escape(term.lower())}\b", lower):
            err(f"{instr}: names grader machinery {term!r}. The instruction must be a "
                "natural persona request, not a description of how it is scored.")

    # Env keys (exact, case-sensitive - they are SHOUTED constants).
    for key in ENV_KEYS:
        if key in text:
            err(f"{instr}: references env key {key!r}. The persona does not know how "
                "the tool surface is wired.")

    # MCP server names. Only the unambiguous ones are banned as bare words -
    # `time`, `memory`, `word`, `excel` are common English words that appear
    # legitimately in instructions, so banning them as words false-positives.
    # (Their tools are still caught by the {server}_-prefixed tool check below.)
    AMBIGUOUS_SERVERS = {"time", "memory", "word", "excel"}
    for server in sorted((known_servers() | {GATEWAY_SERVER}) - AMBIGUOUS_SERVERS):
        if re.search(rf"\b{re.escape(server.lower())}\b", lower):
            err(f"{instr}: names MCP server {server!r}. The persona asks for an outcome, "
                "not a server by name.")

    # Tool IDs, bare and {server}_-prefixed. These are unambiguous snake_case ids.
    banned_tools = known_tools() | prefixed_tools()
    for tool in sorted(banned_tools):
        if re.search(rf"\b{re.escape(tool.lower())}\b", lower):
            err(f"{instr}: names tool {tool!r}. The persona describes the deliverable, "
                "not the tool to build it with.")

    return report("check-instruction-hygiene", task, errors, notes)


if __name__ == "__main__":
    sys.exit(main())
