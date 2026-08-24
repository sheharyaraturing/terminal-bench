#!/usr/bin/env python3
"""Required Harbor task layout files must exist."""
from __future__ import annotations

from _lib import make_err, report, task_arg

REQUIRED = [
    "instruction.md",
    "task.toml",
    "tests/reward.toml",
    "tests/test.sh",
    "solution/solve.sh",
]


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    for rel in REQUIRED:
        if not (task / rel).is_file():
            err(f"{task / rel}: missing (required by the Harbor task layout)")

    # NOTES.md is optional but recommended: it is where the ground-truth
    # derivation, seed spans, and validation commands live (see TASK_FORMAT.md).
    if not (task / "NOTES.md").is_file():
        notes.append("no NOTES.md - optional, but it is the canonical place to record "
                     "the ground-truth derivation and the oracle/nop validation commands.")

    return report("check-required-files", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
