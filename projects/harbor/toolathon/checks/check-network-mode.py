#!/usr/bin/env python3
"""[agent] and [verifier] must not run with network_mode = "public".

Toolathon tasks need no egress: the agent reads local workspace files and talks
to the tool gateway over loopback, and the verifier runs deterministic rewardkit
check functions (no LLM judge, no API key). A public network mode widens the
attack surface for prompt-injection-driven exfiltration and lets a task
accidentally depend on live external state, breaking reproducibility.

Human calibration flagged network_mode = "public" on every reviewed task
("worth one sweep across the suite"), so this check enforces "no-network" on
both sections. An absent key is a NOTE (Harbor's default applies), not a FAIL.
"""
from __future__ import annotations

import sys

from _lib import load_toml, make_err, report, task_arg

ALLOWED = {"no-network"}


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    task_cfg = load_toml(task / "task.toml", err)
    if not task_cfg:
        return report("check-network-mode", task, errors, notes)

    for section in ("agent", "verifier"):
        value = (task_cfg.get(section) or {}).get("network_mode")
        if value is None:
            notes.append(f"[{section}].network_mode is unset - pin it to \"no-network\" "
                         "explicitly so the isolation posture does not drift with "
                         "Harbor defaults.")
        elif value not in ALLOWED:
            err(f"{task}/task.toml: [{section}].network_mode = {value!r}. Toolathon tasks "
                "use local files and a loopback gateway only, and the verifier needs no "
                "network - set \"no-network\".")

    return report("check-network-mode", task, errors, notes)


if __name__ == "__main__":
    sys.exit(main())
