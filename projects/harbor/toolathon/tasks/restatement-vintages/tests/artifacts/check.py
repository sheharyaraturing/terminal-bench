"""The two artifacts the instruction promises exist, are populated, and carry the
promised layout.

Shape only: whether the numbers are right is graded by the latest, original,
revision, definedness and workings dimensions. Nothing here pays for the absence
of damage, and nothing here pays for a stub — every criterion needs the file
present *and* carrying at least one data row, so a workbook holding only the
header row and a workings.json holding only the placeholder skeleton both score
zero across the dimension.

Layout is graded rather than merely stated: policy section 9 fixes the sheet name
and the column order, and sections 3 and 9 fix the row order, so all three are
compared here instead of being dissolved by a dictionary lookup.
"""

import json
from datetime import date, datetime
from pathlib import Path

import rewardkit as rk  # noqa: F401  (imported so the criteria register)
from rewardkit import criterion

SHEET = "Vintage_Report"
REPORT = "vintage_report.xlsx"
WORKINGS = "workings.json"
EXPECTED_SHEET = Path("/tests/expected/vintage_report.xlsx")

COLUMNS = (
    "Period",
    "Latest_Amount_USD",
    "Latest_Vintage_Date",
    "Original_Amount_USD",
    "Original_Vintage_Date",
    "Revision_Pct",
    "Undefined_Reason",
)

KEYS = (
    ("metric",),
    ("reporting_cutoff",),
    ("value",),
    ("undefined",),
    ("undefined_reason",),
    ("denominator",),
    ("periods_defined",),
    ("periods_undefined",),
    ("population", "included"),
    ("population", "excluded", "out_of_scope_period"),
    ("population", "excluded", "management_basis"),
    ("population", "excluded", "after_cutoff"),
    ("population", "excluded", "no_amount"),
    ("population", "excluded", "preliminary"),
)

COUNT_KEYS = (
    ("periods_defined",),
    ("periods_undefined",),
    ("population", "included"),
    ("population", "excluded", "out_of_scope_period"),
    ("population", "excluded", "management_basis"),
    ("population", "excluded", "after_cutoff"),
    ("population", "excluded", "no_amount"),
    ("population", "excluded", "preliminary"),
)


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _pick(workbook):
    """Return (sheet_title, header, data_rows) for the table, from ANY sheet.

    An empty Sheet1 in front is not an error, so every sheet is searched; the
    sheet the policy names wins when more than one carries the header.
    """
    found = []
    for sheet in workbook.worksheets:
        header = None
        rows = []
        for line in sheet.iter_rows(values_only=True):
            cells = [_text(c) for c in (line or ())]
            if header is None:
                low = [c.lower() for c in cells]
                if sum(1 for c in COLUMNS if c.lower() in low) >= 4:
                    header = cells
                continue
            if not any(cells):
                continue
            rows.append(cells)
        if header is not None:
            found.append((sheet.title, header, rows))
    if not found:
        return "", [], []
    for entry in found:
        if entry[0] == SHEET:
            return entry
    return found[0]


def _read(path: Path):
    """Two passes: a formula-written workbook still counts as populated."""
    import openpyxl

    if not path.exists():
        print(f"artifacts: {path.name} was not written to the workspace root")
        return "", [], []
    best = ("", [], [])
    for cached in (True, False):
        try:
            workbook = openpyxl.load_workbook(path, data_only=cached)
        except Exception as exc:
            print(f"artifacts: could not open {path.name}: "
                  f"{type(exc).__name__}: {exc}")
            return "", [], []
        try:
            entry = _pick(workbook)
        finally:
            workbook.close()
        if len(entry[2]) > len(best[2]) or (entry[1] and not best[1]):
            best = entry
    return best


def _spot(header) -> int:
    try:
        return [c.lower() for c in header].index("Period".lower())
    except ValueError:
        return -1


def _periods(rows, header) -> list:
    spot = _spot(header)
    if spot < 0:
        return []
    return [row[spot] for row in _data_rows(rows, header)]


def _data_rows(rows, header):
    """A row counts as data when it labels a period and reports something for it."""
    spot = _spot(header)
    if spot < 0:
        return []
    kept = []
    for row in rows:
        label = row[spot] if spot < len(row) else ""
        if not label:
            continue
        if not any(cell for i, cell in enumerate(row) if i != spot):
            continue
        kept.append(row)
    return kept


@criterion(description="vintage_report.xlsx carries the seven columns the policy fixes, over at least one data row")
def required_columns(workspace: Path) -> float:
    title, header, rows = _read(workspace / REPORT)
    if not header:
        return 0.0
    data = _data_rows(rows, header)
    if not data:
        print(f"artifacts: {SHEET!r} carries a header row and no data row; "
              "a headers-only workbook reports nothing and scores nothing")
        return 0.0
    low = {c.lower() for c in header}
    hits = sum(1 for c in COLUMNS if c.lower() in low)
    if hits < len(COLUMNS):
        print(f"artifacts: header matched {hits} of {len(COLUMNS)} columns "
              f"on sheet {title!r}")
    return hits / len(COLUMNS)


@criterion(description="the sheet name and the column order policy section 9 fixes")
def sheet_layout(workspace: Path) -> float:
    title, header, rows = _read(workspace / REPORT)
    if not header or not _data_rows(rows, header):
        return 0.0
    hits = 0
    if title == SHEET:
        hits += 1
    else:
        print(f"artifacts: the table sits on sheet {title!r}; policy section 9 "
              f"names the sheet {SHEET!r}")
    misplaced = []
    for position, column in enumerate(COLUMNS):
        if position < len(header) and header[position].lower() == column.lower():
            hits += 1
        else:
            actual = header[position] if position < len(header) else "(absent)"
            misplaced.append(f"{position + 1}:{actual!r} not {column!r}")
    if misplaced:
        print("artifacts: column order differs from policy section 9 at "
              + "; ".join(misplaced))
    return hits / (len(COLUMNS) + 1)


@criterion(description="rows in the ascending period order sections 3 and 9 fix")
def row_order(workspace: Path) -> float:
    _t, want_header, want_rows = _read(EXPECTED_SHEET)
    want = _periods(want_rows, want_header)
    if not want:
        print(f"artifacts: the answer key at {EXPECTED_SHEET} did not read; "
              "row order not graded")
        return 0.0
    title, header, rows = _read(workspace / REPORT)
    if not header:
        return 0.0
    got = _periods(rows, header)
    hits = sum(1 for i, period in enumerate(want) if i < len(got) and got[i] == period)
    if hits < len(want):
        print(f"artifacts: {hits} of {len(want)} rows sit in the position ascending "
              f"period order requires; got {got[:12]}")
    return hits / max(len(want), len(got), 1)


@criterion(description="workings.json parses, carries the keys the policy fixes, and accounts for records")
def workings_shape(workspace: Path) -> float:
    path = workspace / WORKINGS
    if not path.exists():
        print(f"artifacts: {WORKINGS} was not written to the workspace root")
        return 0.0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"artifacts: {WORKINGS} is not valid JSON: "
              f"{type(exc).__name__}: {exc}")
        return 0.0
    if not isinstance(payload, dict):
        print(f"artifacts: {WORKINGS} holds a {type(payload).__name__}, "
              "not the object the policy fixes")
        return 0.0

    def dig(path_keys):
        node = payload
        for key in path_keys:
            if not isinstance(node, dict) or key not in node:
                return None
            node = node[key]
        return node

    present = 0
    for path_keys in KEYS:
        node = payload
        for key in path_keys:
            if not isinstance(node, dict) or key not in node:
                break
            node = node[key]
        else:
            present += 1

    counted = 0
    for path_keys in COUNT_KEYS:
        value = dig(path_keys)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            counted += abs(value)
    if counted <= 0:
        print(f"artifacts: {WORKINGS} carries the key skeleton with nothing counted "
              "against it — no period and no register row is accounted for, so the "
              "record accounting reports nothing and scores nothing")
        return 0.0
    return present / len(KEYS)
