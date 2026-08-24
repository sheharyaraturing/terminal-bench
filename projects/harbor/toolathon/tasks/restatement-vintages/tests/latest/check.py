"""Fraction of covered periods carrying the correct latest vintage.

Graded apart from the original-vintage half so an agent that computed the
easy column and stopped is distinguishable from one that computed both and
got them wrong.
"""

import rewardkit as rk  # noqa: F401  (imported so the criteria register)
from rewardkit import criterion

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

EXPECTED_SHEET = Path("/tests/expected/vintage_report.xlsx")
REPORT = "vintage_report.xlsx"
TOLERANCE = Decimal("0.00001")


def _text(value) -> str:
    """A cell as comparable text. Dates normalise to YYYY-MM-DD, floats to ints."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _date_text(value) -> str:
    """Dates written as text, as datetimes, or as 'YYYY-MM-DD 00:00:00' all collapse."""
    raw = _text(value)
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-" and raw[:4].isdigit():
        head = raw[:10]
        if head[5:7].isdigit() and head[8:10].isdigit():
            return head
    return raw


def _number(value):
    """Strict: policy section 9 bars the currency symbol, the thousands separator
    and the percent sign, so a cell carrying one of them is not a number here."""
    raw = _text(value)
    if not raw:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def _scan(workbook, columns):
    """Find the header row in ANY sheet — never trust the active one.

    Returns (table, coords, sheet_title): the cell values keyed by period, the
    cell coordinates behind them so a failure can be reported at its address,
    and the title of the sheet the table was found on.
    """
    wanted = [c.lower() for c in columns]
    for sheet in workbook.worksheets:
        index = None
        table: dict = {}
        coords: dict = {}
        for row in sheet.iter_rows():
            values = [_text(cell.value).lower() for cell in row]
            if index is None:
                if all(w in values for w in wanted):
                    index = {c: values.index(c.lower()) for c in columns}
                continue
            if all(cell.value is None for cell in row):
                continue
            spot = index["Period"]
            key = _text(row[spot].value).upper() if spot < len(row) else ""
            if not key:
                continue
            table[key] = {
                c: (row[index[c]].value if index[c] < len(row) else None)
                for c in columns
            }
            coords[key] = {
                c: (row[index[c]].coordinate if index[c] < len(row) else "?")
                for c in columns
            }
        if index is not None:
            return table, coords, sheet.title
    return {}, {}, ""


def _table(path: Path, columns, dimension: str):
    """Read the report, tolerating cells an agent wrote as Excel formulas.

    load_workbook(data_only=True) returns the cached result, and a workbook a
    program wrote without ever opening Excel has no cache — so every formula cell
    reads None. Read twice and fall back per cell rather than scoring it zero, and
    name the formula at its address so a debugger is not sent after a phantom
    blank cell. One line per affected sheet, not one per cell.
    """
    import openpyxl

    if not path.exists():
        return {}
    reads = []
    for cached in (True, False):
        try:
            workbook = openpyxl.load_workbook(path, data_only=cached)
        except Exception as exc:
            print(f"{dimension}: could not open {path.name}: "
                  f"{type(exc).__name__}: {exc}")
            return {}
        try:
            reads.append(_scan(workbook, columns))
        finally:
            workbook.close()
    (values, _vc, _vt), (formulas, coords, title) = reads
    if not values:
        merged = dict(formulas)
    else:
        merged = {}
        for key in set(values) | set(formulas):
            row = dict(formulas.get(key, {}))
            row.update({c: v for c, v in values.get(key, {}).items() if _text(v) != ""})
            merged[key] = row

    announced = set()
    for key in sorted(merged):
        for column in columns:
            cell = merged[key].get(column)
            if not (isinstance(cell, str) and cell.startswith("=")):
                continue
            if title in announced:
                continue
            announced.add(title)
            coord = coords.get(key, {}).get(column, "?")
            print(f"{dimension}: {title}!{coord} holds the formula {cell!r} and no "
                  "cached value; policy section 9 requires recorded values, not formulas")
    return merged


def _cell_match(got, want, kind) -> bool:
    """want comes from the answer key, so its type says how to compare."""
    if isinstance(want, str):
        if want == "UNDEFINED":
            # 0, "", None, an absent cell and 'undefined' are all wrong, and all
            # land here: section 6 fixes UNDEFINED as the exact spelling.
            return _text(got) == "UNDEFINED"
        if kind == "date":
            return _date_text(got) == _date_text(want)
        return _text(got) == want.strip()
    left, right = _number(got), _number(want)
    if left is None or right is None:
        return False
    if kind == "money":
        return left == right
    return abs(left - right) <= TOLERANCE


def _score(workspace: Path, columns, kinds, label) -> float:
    want = _table(EXPECTED_SHEET, columns, label)
    if not want:
        print(f"{label}: the answer key at {EXPECTED_SHEET} did not read; grading aborted")
        return 0.0
    got = _table(workspace / REPORT, columns, label)
    hits = 0
    for period, row in want.items():
        mine = got.get(period)
        if mine is None:
            continue
        if all(_cell_match(mine.get(c), row[c], kinds[c]) for c in columns if c != "Period"):
            hits += 1
    return hits / max(len(want), len(got), 1)

COLUMNS = ("Period", "Latest_Amount_USD", "Latest_Vintage_Date")
KINDS = {"Latest_Amount_USD": "money", "Latest_Vintage_Date": "date"}


@criterion(description="latest vintage amount and vintage date per covered period")
def latest_vintage(workspace: Path) -> float:
    return _score(workspace, COLUMNS, KINDS, "latest_vintage")
