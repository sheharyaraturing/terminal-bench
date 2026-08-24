#!/usr/bin/env python3
"""tests/ dimension dirs: the per-dimension scoring logic must exist and use rewardkit.

Toolathon grades each task via one tests/<dimension>/check.py per graded dimension,
aggregated by the [[reward]] blocks. This is toolathon's analogue of trialforge's
criterion-count check - it verifies the scoring logic actually exists.

Enforces (100% consistent across all 16 tasks):
  - tests/expected/ exists (the baked answer key)
  - every tests/ subdirectory except expected/ contains a check.py
  - each such check.py imports from rewardkit (the @criterion decorator source)
  - at least one dimension dir exists besides expected/
"""
from __future__ import annotations

import re
import sys

from _lib import make_err, read_text, report, task_arg

REWARDKIT_IMPORT = re.compile(r"^\s*(from\s+rewardkit\s+import|import\s+rewardkit)\b", re.M)
# Dirs under tests/ that are data, not graded dimensions.
DATA_DIRS = {"expected"}


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    tests = task / "tests"
    if not tests.is_dir():
        err(f"{tests}: missing (check-required-files also enforces this)")
        return report("check-criterion-dirs", task, errors, notes)

    if not (tests / "expected").is_dir():
        err(f"{tests}/expected: missing. The answer key the dimension checks grade "
            "against is baked here.")

    dim_dirs = sorted(
        p for p in tests.iterdir()
        if p.is_dir() and p.name not in DATA_DIRS
    )
    if not dim_dirs:
        err(f"{tests}: no dimension directories. Each graded dimension needs a "
            "tests/<dimension>/check.py; without any, the [[reward]] blocks have "
            "nothing to aggregate.")

    for d in dim_dirs:
        check = d / "check.py"
        if not check.is_file():
            err(f"{check}: missing. Every tests/<dimension>/ dir grades one dimension "
                "via a check.py.")
            continue
        if not REWARDKIT_IMPORT.search(read_text(check)):
            err(f"{check}: does not import from rewardkit. Dimension checks score via "
                "the @criterion decorator (from rewardkit import criterion).")

    notes.append(f"{len(dim_dirs)} dimension dir(s): {', '.join(d.name for d in dim_dirs)}")
    return report("check-criterion-dirs", task, errors, notes)


if __name__ == "__main__":
    sys.exit(main())
