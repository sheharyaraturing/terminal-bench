#!/usr/bin/env python3
"""[metadata] bounds: persona, domain, target_tool_calls.

These drive the suite's distribution reporting and the quality bar in
CONTRIBUTING.md. This check enforces the ABSOLUTE ranges only.

target_claims is intentionally NOT range-checked: the suite fixes no min/max on
the claim count. Its only contract is target_claims == the [[criterion]] count,
which check-claims-consistency owns - the two complement rather than duplicate
each other.
"""
from __future__ import annotations

from _lib import (DOMAINS, MAX_TOOL_CALLS, MIN_TOOL_CALLS, load_toml,
                  make_err, report, task_arg)


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

    # target_claims has no absolute band: the suite fixes no min/max on the
    # number of atomic claims. Its only contract is target_claims == the
    # [[criterion]] count, which check-claims-consistency owns. We deliberately
    # do not range-check the value here.

    return report("check-metadata-bounds", task, errors, [])


if __name__ == "__main__":
    raise SystemExit(main())
