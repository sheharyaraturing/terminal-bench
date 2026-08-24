"""The consolidated register, graded twice.

`register` is the whole sheet: every column the standard names is compared, so a row
is a hit only when all eleven cells agree. Extra rows -- an unmerged cluster member
left behind, or a near-duplicate wrongly folded away -- count against the denominator,
so neither padding nor over-merging can raise the score.

`consolidated_rows` is the handful of rows consolidation actually moves, because the
whole-sheet fraction is dominated by the several hundred vendors nobody touches: an
agent that copies the extract across unchanged would otherwise read as almost right.
Which rows those are comes from the answer key, not from this file. Clusters the
standard refuses to consolidate are left to the restraint dimension, so that keeping
them intact is never paid for on its own.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from rewardkit import criterion

EXPECTED = Path("/tests/expected/vendor_master_merged.xlsx")
EXPECTED_LOG = Path("/tests/expected/merge_log.xlsx")
LOG_COLUMNS = ("Survivor", "Losers")
COLUMNS = (
    "VendorID", "LegalName", "TaxID", "RemitToAddress", "RemitToPostcode",
    "Country", "PaymentTerms", "ContactEmail", "DeptCode", "SpendYTD", "LastUpdated",
)


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


def _keyed(path: Path, label: str) -> dict[str, tuple[str, ...]]:
    _, rows = _table(path, COLUMNS, label)
    out: dict[str, tuple[str, ...]] = {}
    for row in rows:
        vendor = _scalar(row.get("VendorID"))
        if vendor:
            out[vendor] = tuple(_scalar(row.get(c)) for c in COLUMNS)
    return out


@criterion(description="consolidated vendor rows matching the standard's outcome")
def register(workspace: Path) -> float:
    expected = _keyed(EXPECTED, "register/expected")
    if not expected:
        return 0.0
    got = _keyed(workspace / "vendor_master_merged.xlsx", "register")
    if not got:
        return 0.0
    hits = sum(1 for vendor, row in expected.items() if got.get(vendor) == row)
    misses = [v for v, row in expected.items() if got.get(v) != row]
    if misses:
        print(f"register: {len(misses)} of {len(expected)} rows differ, "
              f"first few {sorted(misses)[:6]}")
    extra = sorted(set(got) - set(expected))
    if extra:
        print(f"register: {len(extra)} row(s) the standard does not keep, "
              f"first few {extra[:6]}")
    return hits / max(len(expected), len(got))


def _clusters(path: Path, label: str) -> list[tuple[str, list[str]]]:
    """(survivor, losers) for every cluster the answer key records."""
    _, rows = _table(path, LOG_COLUMNS, label)
    out = []
    for row in rows:
        survivor = _scalar(row.get("Survivor"))
        losers = [p.strip() for p in re.split(r"[;,]", _scalar(row.get("Losers"))) if p.strip()]
        if survivor:
            out.append((survivor, losers))
    return out


@criterion(description="the rows consolidation moves: survivors rewritten, absorbed rows gone")
def consolidated_rows(workspace: Path) -> float:
    expected = _keyed(EXPECTED, "consolidated/expected")
    clusters = _clusters(EXPECTED_LOG, "consolidated/expected")
    if not expected or not clusters:
        return 0.0
    got = _keyed(workspace / "vendor_master_merged.xlsx", "consolidated")
    if not got:
        return 0.0

    hits = total = 0
    for survivor, losers in clusters:
        members = [survivor, *losers]
        if all(m in expected for m in members):
            # a cluster the standard holds rather than consolidates; graded elsewhere
            continue
        total += 1
        if got.get(survivor) == expected.get(survivor):
            hits += 1
        else:
            print(f"consolidated: {survivor} is not the row the standard consolidates to")
        for loser in losers:
            total += 1
            if loser in got:
                print(f"consolidated: {loser} was absorbed into {survivor} "
                      "but still stands as its own row")
            else:
                hits += 1
    return hits / total if total else 0.0
