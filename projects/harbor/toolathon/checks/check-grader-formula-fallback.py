#!/usr/bin/env python3
"""Graders that read xlsx values must tolerate formula-written workbooks.

openpyxl's `load_workbook(path, data_only=True)` returns CACHED values. A
workbook written by a program that never ran Excel (openpyxl, the excel MCP
server) stores no cache for formula cells, so every formula cell reads as None -
and a correct answer written the most natural way (`=(C2-B2)/B2*100`, the very
thing the excel tool is FOR) scores zero with a misleading "got '(blank)'".

Measured in human calibration of segment-growth and vendor-outliers (2026-08-19):
an otherwise perfect formula-written answer failed 23/32 cells.

Acceptable patterns (detected via AST, so docstrings discussing the issue do
not count):

    data = openpyxl.load_workbook(path, data_only=True)   # cached values
    raw  = openpyxl.load_workbook(path, data_only=False)  # formulas as text

or the parameterized dual-load (restatement-vintages):

    for cached in (True, False):
        wb = openpyxl.load_workbook(path, data_only=cached)

or evaluating formulas directly via the `formulas` library.

Graders that route through rewardkit helpers (import rewardkit, no direct
openpyxl) keep their read logic in the installed package and cannot be
inspected here - they are skipped.
"""
from __future__ import annotations

import ast
import sys

from _lib import make_err, read_text, report, task_arg


def _data_only_values(tree: ast.AST) -> list[object]:
    """The data_only= argument of every load_workbook call: True/False literals,
    or None for a non-literal (parameterized) argument."""
    values: list[object] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else (
            func.id if isinstance(func, ast.Name) else "")
        if name != "load_workbook":
            continue
        for kw in node.keywords:
            if kw.arg != "data_only":
                continue
            if isinstance(kw.value, ast.Constant) and kw.value.value in (True, False):
                values.append(kw.value.value)
            else:
                values.append(None)  # parameterized, e.g. data_only=cached
    return values


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    tests = task / "tests"
    if not tests.is_dir():
        return report("check-grader-formula-fallback", task, errors,
                      ["no tests/ dir; see check-required-files"])

    checked = 0
    for check in sorted(tests.glob("*/check.py")):
        text = read_text(check)
        try:
            tree = ast.parse(text, filename=str(check))
        except SyntaxError:
            continue  # unparseable graders are check-criterion-dirs' problem
        values = _data_only_values(tree)
        if True not in values:
            continue  # never reads cached values; nothing to guard
        checked += 1
        has_fallback = (
            False in values
            or None in values  # parameterized dual-load: data_only=cached
            or any(
                isinstance(n, ast.Import) and any(a.name == "formulas" for a in n.names)
                for n in ast.walk(tree)
            )
        )
        if not has_fallback:
            err(f"{check}: loads with data_only=True but never loads with data_only=False. "
                "A formula-written workbook reads every computed cell as blank, so a correct "
                "answer produced the idiomatic way (excel MCP formulas) scores zero. Dual-load "
                "and fall back for blank cells - see bank-recon/tests/matched/check.py or "
                "restatement-vintages/tests/definedness/check.py.")

    if checked:
        notes.append(f"{checked} grader(s) read cached xlsx values")
    return report("check-grader-formula-fallback", task, errors, notes)


if __name__ == "__main__":
    sys.exit(main())
