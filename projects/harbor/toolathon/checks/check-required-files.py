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
    "environment/Dockerfile",
    "environment/runtime/setup.sh",
    "tests/expected",
]


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    for rel in REQUIRED:
        if not (task / rel).exists():
            err(f"{task / rel}: missing (required by the toolathon task layout)")

    # README.md is present in 13/16 tasks; recommend it but don't require it.
    if not (task / "README.md").is_file():
        notes.append("no README.md - optional, but recommended as the human-facing "
                     "task summary.")

    return report("check-required-files", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
