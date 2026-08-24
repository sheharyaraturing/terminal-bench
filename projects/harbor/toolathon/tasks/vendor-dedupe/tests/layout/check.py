"""The output shape sections 9 and 10 of the standard actually state.

The standard does not only say what the answer is, it says what it looks like: the
consolidated register sits on a sheet named `VendorMaster` carrying the extract's
eleven columns in the extract's order with its rows in ascending `VendorID` order,
and the merge log sits on a sheet named `MergeLog` carrying `Survivor`, `Losers`,
`FieldsTaken`, `Status` in that order, its rows in ascending `Survivor` order, with
`Losers` ascending and `FieldsTaken` in the extract's column order, each joined with
a semicolon and no spaces. Every one of those sentences is graded here, because a
requirement the spec states and the grader never looks at is a requirement the task
does not have.

Shape only. Which rows belong in the sheet and what they say is the business of the
`register`, `mergelog` and `restraint` dimensions; this file asks where things sit
and how the two list cells are written, so an agent is not charged twice for one
mistake. Every criterion is a fraction -- of columns in the stated position, of rows
in the stated position, of list cells written in the stated form -- never a boolean,
and every one of them is zero for a sheet that carries a header row and nothing
under it.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from rewardkit import criterion

REGISTER = "vendor_master_merged.xlsx"
REGISTER_SHEET = "VendorMaster"
COLUMNS = (
    "VendorID", "LegalName", "TaxID", "RemitToAddress", "RemitToPostcode",
    "Country", "PaymentTerms", "ContactEmail", "DeptCode", "SpendYTD", "LastUpdated",
)
LOG = "merge_log.xlsx"
LOG_SHEET = "MergeLog"
LOG_COLUMNS = ("Survivor", "Losers", "FieldsTaken", "Status")

# Section 11 publishes these two; either is a whole FieldsTaken cell on its own and
# neither is a semicolon list, so the join rule does not apply to them.
MARKERS = ("none", "not applicable")


def _scalar(value) -> str:
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


def _sheet(path: Path, sheet: str, label: str):
    """(header cells, data rows) of the sheet with that name, read as written.

    Read without `data_only` so that a formula cell arrives as its formula text: this
    dimension asks where a value sits, and a cell holding `=A2` still sits somewhere.
    Formulas are not evaluated here or anywhere else in this verifier; the graders
    that compare values name the offending cell.
    """
    import openpyxl

    if not path.exists():
        print(f"layout: {path.name} was not produced")
        return None, None
    try:
        wb = openpyxl.load_workbook(path, data_only=False)
    except Exception as exc:
        print(f"layout: could not open {path.name}: {type(exc).__name__}: {exc}")
        return None, None
    match = next((n for n in wb.sheetnames if n.strip().casefold() == sheet.casefold()), None)
    if match is None:
        print(f"layout: {path.name} has no sheet named {sheet!r}; it carries "
              f"{wb.sheetnames}, and {label} of the standard names the sheet")
        return None, None
    rows = list(wb[match].iter_rows(values_only=True))
    if not rows:
        print(f"layout: {path.name} sheet {sheet!r} is empty")
        return None, None
    header = list(rows[0])
    while header and header[-1] is None:
        header.pop()
    data = [r for r in rows[1:]
            if r is not None and any(c is not None and str(c).strip() for c in r)]
    if not data:
        print(f"layout: {path.name} sheet {sheet!r} carries a header row and no data "
              "rows; there is no layout to grade")
        return header, None
    return header, data


def _column_order(path: Path, sheet: str, columns: tuple[str, ...], label: str) -> float:
    """Fraction of the stated columns that sit where the standard puts them."""
    header, data = _sheet(path, sheet, label)
    if header is None or data is None:
        return 0.0
    seen = ["".join(str(c).split()).casefold() if c is not None else "" for c in header]
    want = [c.casefold() for c in columns]
    hits = sum(1 for i, name in enumerate(want) if i < len(seen) and seen[i] == name)
    if hits != len(want):
        print(f"layout: {path.name} sheet {sheet!r} header is {header}, and {label} "
              f"requires {list(columns)} in that order")
    return hits / max(len(want), len(seen))


def _row_order(path: Path, sheet: str, columns: tuple[str, ...], key: str,
               label: str) -> float:
    """Fraction of data rows whose key sits in the position ascending order puts it."""
    header, data = _sheet(path, sheet, label)
    if header is None or data is None:
        return 0.0
    seen = ["".join(str(c).split()).casefold() if c is not None else "" for c in header]
    if key.casefold() not in seen:
        print(f"layout: {path.name} sheet {sheet!r} has no {key} column, so its row "
              "order cannot be read")
        return 0.0
    pos = seen.index(key.casefold())
    keys = [_scalar(r[pos]) if pos < len(r) else "" for r in data]
    ordered = sorted(keys)
    hits = sum(1 for a, b in zip(keys, ordered) if a == b)
    if hits != len(keys):
        first = next(i for i, (a, b) in enumerate(zip(keys, ordered)) if a != b)
        print(f"layout: {path.name} sheet {sheet!r} is not in ascending {key} order -- "
              f"{hits} of {len(keys)} rows sit in the right place, and row {first + 2} "
              f"holds {keys[first]!r} where ascending order puts {ordered[first]!r}; "
              f"{label} requires ascending {key} order")
    return hits / len(keys)


def _joined(raw) -> list[str] | None:
    """The parts of a semicolon list written as the standard requires, or None.

    `a;b` is a list. `a; b`, `a,b` and a trailing separator are not: section 10 says
    joined with a semicolon and no spaces.
    """
    if raw is None:
        return None
    text = str(raw)
    if not text or text != text.strip() or re.search(r"\s", text):
        return None
    parts = text.split(";")
    if any(not p for p in parts):
        return None
    return parts


@criterion(description="the register's sheet name and column order, as section 9 states them")
def register_column_order(workspace: Path) -> float:
    return _column_order(workspace / REGISTER, REGISTER_SHEET, COLUMNS, "section 9")


@criterion(description="the register's rows in ascending VendorID order, as section 9 states")
def register_row_order(workspace: Path) -> float:
    return _row_order(workspace / REGISTER, REGISTER_SHEET, COLUMNS, "VendorID", "section 9")


@criterion(description="the merge log's sheet name and column order, as section 10 states them")
def merge_log_column_order(workspace: Path) -> float:
    return _column_order(workspace / LOG, LOG_SHEET, LOG_COLUMNS, "section 10")


@criterion(description="the merge log's rows in ascending Survivor order, as section 10 states")
def merge_log_row_order(workspace: Path) -> float:
    return _row_order(workspace / LOG, LOG_SHEET, LOG_COLUMNS, "Survivor", "section 10")


@criterion(description="Losers ascending and FieldsTaken in the extract's column order")
def merge_log_list_cells(workspace: Path) -> float:
    """Fraction of the log's two list cells written the way section 10 states.

    Whether the right vendors and the right fields are named is the `mergelog`
    dimension's question. This one asks only whether the cell is a semicolon list
    with no spaces, whether `Losers` ascends, and whether `FieldsTaken` runs in the
    extract's column order -- three sentences of section 10 that a dictionary lookup
    never reads.
    """
    path = workspace / LOG
    header, data = _sheet(path, LOG_SHEET, "section 10")
    if header is None or data is None:
        return 0.0
    seen = ["".join(str(c).split()).casefold() if c is not None else "" for c in header]
    hits = total = 0
    order = {c.casefold(): i for i, c in enumerate(COLUMNS)}

    for offset, row in enumerate(data):
        def cell(name: str):
            if name.casefold() not in seen:
                return None
            pos = seen.index(name.casefold())
            return row[pos] if pos < len(row) else None

        total += 2
        line = offset + 2
        losers = _joined(cell("Losers"))
        if losers is None:
            print(f"layout: {LOG} row {line} Losers is {cell('Losers')!r}; section 10 "
                  "joins the VendorIDs with a semicolon and no spaces")
        elif losers != sorted(losers):
            print(f"layout: {LOG} row {line} Losers {cell('Losers')!r} is not ascending")
        else:
            hits += 1

        raw = cell("FieldsTaken")
        text = _scalar(raw)
        if text in MARKERS:
            hits += 1
            continue
        fields = _joined(raw)
        if fields is None:
            print(f"layout: {LOG} row {line} FieldsTaken is {raw!r}; section 10 joins "
                  "the field names with a semicolon and no spaces")
            continue
        keys = [f.casefold() for f in fields]
        if any(k not in order for k in keys):
            print(f"layout: {LOG} row {line} FieldsTaken {raw!r} names something that "
                  "is not a column of the extract")
        elif [order[k] for k in keys] != sorted(order[k] for k in keys):
            print(f"layout: {LOG} row {line} FieldsTaken {raw!r} is not in the "
                  "extract's column order")
        else:
            hits += 1

    return hits / total if total else 0.0
