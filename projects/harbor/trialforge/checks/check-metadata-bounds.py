#!/usr/bin/env python3
"""[metadata] bounds: persona, domain, target_tool_calls, target_claims.

These drive the suite's distribution reporting and the quality bar in
CONTRIBUTING.md. This check enforces the ABSOLUTE ranges only. The RELATIVE
contract that target_claims must equal the [[criterion]] count is owned by
check-claims-consistency - the two complement rather than duplicate each other.
"""
from __future__ import annotations

from _lib import (DOMAINS, MAX_CLAIMS, MAX_TOOL_CALLS, MIN_CLAIMS,
                  MIN_TOOL_CALLS, load_toml, make_err, report, task_arg)


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    err = make_err(errors)

    task_cfg = load_toml(task / "task.toml", err)
    meta = task_cfg.get("metadata") or {}

    persona = str(meta.get("persona") or "").strip()
    if not persona:
        err(f"{task}/task.toml: [metadata].persona is required - the prompt is written "
            "in a named persona's voice and the metadata should say which.")

    domain = str(meta.get("domain") or "").strip()
    if domain not in DOMAINS:
        err(f"{task}/task.toml: [metadata].domain = {domain!r}, expected one of "
            f"{sorted(DOMAINS)}.")

    calls = meta.get("target_tool_calls")
    if not isinstance(calls, (int, float)) or not (MIN_TOOL_CALLS <= calls <= MAX_TOOL_CALLS):
        err(f"{task}/task.toml: [metadata].target_tool_calls = {calls!r}, expected "
            f"{MIN_TOOL_CALLS}-{MAX_TOOL_CALLS} (the long-horizon band).")

    target_claims = meta.get("target_claims")
    if isinstance(target_claims, (int, float)):
        if not (MIN_CLAIMS <= target_claims <= MAX_CLAIMS):
            err(f"{task}/task.toml: [metadata].target_claims = {target_claims!r}, expected "
                f"{MIN_CLAIMS}-{MAX_CLAIMS}.")

    return report("check-metadata-bounds", task, errors, [])


if __name__ == "__main__":
    raise SystemExit(main())
