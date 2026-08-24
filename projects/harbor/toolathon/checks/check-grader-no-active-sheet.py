#!/usr/bin/env python3
"""Graders must never read the workbook's .active sheet.

An agent that leaves an empty leading Sheet1 in front of its real answer sheet
is CORRECT - but a grader that reads `wb.active` (or selects the active sheet
any other way) grades the empty sheet and fails it. Every toolathon grader
selects sheets by name or scans every sheet for the expected header; the
docstrings say so explicitly ("never trust .active").

Human calibration listed `.active` as a latent issue on every reviewed task.
This check is the regression guard: it parses each tests/**/check.py with ast
(so comments and docstrings don't false-positive) and fails on any attribute
read named `active` on a workbook-like object.
"""
from __future__ import annotations

import ast
import sys

from _lib import make_err, read_text, report, task_arg


def _active_reads(path, text: str, err) -> None:
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return  # unparseable graders are check-criterion-dirs' problem, not this one's
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "active":
            err(f"{path}:{node.lineno}: reads `.active`. An agent that leaves an empty "
                "leading sheet in front of its answer is correct; grade sheets by name "
                "or scan every sheet for the expected header instead.")


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    tests = task / "tests"
    if not tests.is_dir():
        return report("check-grader-no-active-sheet", task, errors,
                      ["no tests/ dir; see check-required-files"])

    for check in sorted(tests.glob("*/check.py")):
        _active_reads(check, read_text(check), err)

    return report("check-grader-no-active-sheet", task, errors, notes)


if __name__ == "__main__":
    sys.exit(main())
