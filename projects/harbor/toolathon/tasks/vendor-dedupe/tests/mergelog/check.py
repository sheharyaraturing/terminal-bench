"""Fraction of the merge log's rows that match the standard's outcome.

Keyed on Survivor, comparing Losers, FieldsTaken and Status together: a cluster
counts only when the agent found the same members, took the same fields from
outside the survivor, and reached the same disposition. Clusters the agent invented
count against the denominator, so over-merging lowers the score.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from rewardkit import criterion

EXPECTED = Path("/tests/expected/merge_log.xlsx")
COLUMNS = ("Survivor", "Losers", "FieldsTaken", "Status")


def _scalar(value) -> str:
    """One cell, reduced to the form both sides are compared in."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float, Decimal)):
        text = format(Decimal(str(value)), "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return " ".join(str(value).split()).casefold()


def _table(path: Path, required: tuple[str, ...], label: str):
    """Header and rows of the first sheet carrying every required column.

    Read twice. `data_only=True` returns Excel's cached values, and a workbook
    written by a program that never ran Excel has no cache, so a formula cell reads
    as None; the second read supplies whatever the cell actually holds, so a formula
    cell arrives here as its formula text rather than as an empty one.

    Formulas are not evaluated. openpyxl cannot evaluate them and this verifier has
    no formula engine, and section 9 of the standard asks for recorded values, so a
    formula cell is simply compared as the text it holds and scores wrong. What is
    reported is the cause: the first offending cell on each sheet is named by its
    coordinate, once per sheet rather than once per cell, so a wholly formula-written
    answer names the problem instead of flooding the log with phantom blanks.
    """
    import openpyxl
    from openpyxl.utils import get_column_letter

    if not path.exists():
        print(f"{label}: {path.name} was not produced")
        return None, []
    try:
        cached = openpyxl.load_workbook(path, data_only=True)
    except Exception as exc:
        print(f"{label}: could not open {path.name}: {type(exc).__name__}: {exc}")
        return None, []
    try:
        raw = openpyxl.load_workbook(path, data_only=False)
    except Exception:
        raw = cached

    wanted = {c.casefold() for c in required}
    for name in cached.sheetnames:
        rows_c = list(cached[name].iter_rows(values_only=True))
        rows_r = list(raw[name].iter_rows(values_only=True)) if name in raw.sheetnames else rows_c
        if not rows_c:
            continue
        header = ["".join(str(c).split()).casefold() if c is not None else "" for c in rows_c[0]]
        if not wanted.issubset(set(header)):
            continue
        index = {col: header.index(col.casefold()) for col in required if col.casefold() in header}
        out = []
        formulas: list[tuple[tuple[int, int], str, str]] = []
        for i, row_c in enumerate(rows_c[1:], start=1):
            row_r = rows_r[i] if i < len(rows_r) else row_c
            if row_c is None or all(c is None for c in row_c):
                continue
            record = {}
            for col, pos in index.items():
                value = row_c[pos] if pos < len(row_c) else None
                if value is None and pos < len(row_r) and row_r[pos] is not None:
                    value = row_r[pos]
                    if isinstance(value, str) and value.startswith("="):
                        coord = f"{get_column_letter(pos + 1)}{i + 1}"
                        formulas.append(((i, pos), coord, value))
                record[col] = value
            out.append(record)
        if formulas:
            formulas.sort(key=lambda f: f[0])
            _, coord, text = formulas[0]
            print(f"{label}: {name}!{coord} holds the formula {text!r} and no cached "
                  "value; section 9 of Data Governance Standard DG-114 requires "
                  "recorded values, not formulas")
            if len(formulas) > 1:
                print(f"{label}: {len(formulas) - 1} further formula cell(s) on sheet "
                      f"{name!r} are read the same way and are not reported "
                      "individually")
        return name, out
    print(f"{label}: no sheet in {path.name} carries the columns {list(required)}")
    return None, []


def _list(value):
    """A semicolon list, or None when the cell carries no list at all.

    None is returned for an empty cell so that a blank, a zero and a missing row
    are all distinct from the two published markers rather than collapsing onto
    one of them.
    """
    text = _scalar(value)
    if not text:
        return None
    parts = [p.strip() for p in re.split(r"[;,]", text) if p.strip()]
    return tuple(sorted(parts)) if parts else None


def _keyed(path: Path, label: str) -> dict[str, tuple]:
    _, rows = _table(path, COLUMNS, label)
    out: dict[str, tuple] = {}
    for row in rows:
        survivor = _scalar(row.get("Survivor"))
        if survivor:
            out[survivor] = (
                _list(row.get("Losers")),
                _list(row.get("FieldsTaken")),
                _scalar(row.get("Status")),
            )
    return out


@criterion(description="merge-log clusters matching the standard's outcome")
def mergelog(workspace: Path) -> float:
    expected = _keyed(EXPECTED, "mergelog/expected")
    if not expected:
        return 0.0
    got = _keyed(workspace / "merge_log.xlsx", "mergelog")
    if not got:
        return 0.0
    hits = 0
    for survivor, want in expected.items():
        have = got.get(survivor)
        if have == want:
            hits += 1
        else:
            print(f"mergelog: {survivor} expected {want}, got {have}")
    extra = sorted(set(got) - set(expected))
    if extra:
        print(f"mergelog: {len(extra)} cluster(s) the standard does not identify: {extra[:6]}")
    return hits / max(len(expected), len(got))
