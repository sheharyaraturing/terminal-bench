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

    # NOTES.md must NOT ship in the task folder. It becomes an answer key nobody
    # remembers is there (see the rubric's task_folder_holds_only_task_files).
    # The ground-truth derivation belongs in the reward.toml header; any overflow
    # belongs in the review record (PR / QA report), outside the task folder.
    if (task / "NOTES.md").is_file():
        notes.append("NOTES.md is present at the task root - it must not ship. Move the "
                     "ground-truth derivation into the reward.toml header and any overflow "
                     "into the review record (PR/QA), then delete NOTES.md.")

    return report("check-required-files", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
