"""The two artifacts the instruction promised, and the layout they must carry.

Shape only — the figures are graded by tests/fees and tests/workings. Four
fractions:

  fees_columns     the Fees sheet names the four columns the run reports
  fees_layout      the sheet is named Fees, the header sits in row 1, and the
                   four columns stand in the order section 10 fixes
  fees_row_order   the data rows stand in the order section 10 fixes, one
                   account per row, ascending
  workings_keys    workings.json parses and carries the nine keys, populated

Every one of them requires data beneath the header. A workbook that carries the
right header and nothing under it, or a JSON object whose nine keys are all null,
is an empty shell and scores zero here rather than banking a third of the reward
for shape it did not have to earn.

The workbook is read literally rather than through openpyxl's cached-value view:
a cell holding a formula still counts as a written row for the purpose of layout,
and whether the figure in it is usable is tests/fees' business, not this
dimension's.
"""

import json
from pathlib import Path

from rewardkit import criterion

EXPECTED = Path("/tests/expected/fee_schedule_run.xlsx")
WORKBOOK = "fee_schedule_run.xlsx"
SHEET = "fees"
COLUMNS = ("account", "balance", "fee", "effectiverate")
KEYS = (
    "metric", "schedule_version", "snapshot_date", "accounts_in_file",
    "accounts_reported", "total_fee_cents", "excluded", "undefined",
    "band_balance_cents",
)


def _norm(value) -> str:
    return "" if value is None else str(value).strip().lower().replace(" ", "")


def _sheets(path: Path) -> list[tuple[str, list[list]]]:
    """(title, rows) for every worksheet, read literally. Never trusts .active."""
    import openpyxl

    if not path.exists():
        return []
    try:
        book = openpyxl.load_workbook(path, data_only=False)
    except Exception as exc:
        print(f"artifacts: could not open {path}: {type(exc).__name__}: {exc}")
        return []
    return [(sheet.title, [list(r) for r in sheet.iter_rows(values_only=True)])
            for sheet in book.worksheets]


def _filled(row: list) -> bool:
    return any(c is not None and str(c).strip() != "" for c in row)


def _header_index(rows: list[list]) -> int:
    """Index of the first row naming all four columns, or -1."""
    for i, row in enumerate(rows):
        header = {_norm(c) for c in row if c is not None}
        if all(c in header for c in COLUMNS):
            return i
    return -1


def _accounts(path: Path) -> list[str]:
    """The Account column, in the order the sheet writes it."""
    for _title, rows in _sheets(path):
        i = _header_index(rows)
        if i < 0:
            continue
        header = [_norm(c) for c in rows[i]]
        col = header.index("account")
        out = []
        for row in rows[i + 1:]:
            if not _filled(row):
                continue
            value = row[col] if col < len(row) else None
            text = "" if value is None else str(value).strip()
            if text:
                out.append(text)
        return out
    return []


@criterion(description="fee_schedule_run.xlsx names the four columns the run reports, over data rows")
def fees_columns(workspace: Path) -> float:
    path = workspace / WORKBOOK
    sheets = _sheets(path)
    if not sheets:
        print(f"fees_columns: {WORKBOOK} is absent or unreadable")
        return 0.0

    best = 0.0
    header_seen = False
    for _title, rows in sheets:
        for i, row in enumerate(rows):
            header = {_norm(c) for c in row if c is not None}
            hits = sum(1 for c in COLUMNS if c in header)
            if not hits:
                continue
            header_seen = True
            if not any(_filled(r) for r in rows[i + 1:]):
                continue
            best = max(best, hits / len(COLUMNS))
    if best == 0.0 and header_seen:
        print(f"fees_columns: {WORKBOOK} carries a header row but no data row "
              "beneath it; section 10 asks for one row per account in the run")
    elif best < 1.0:
        print(f"fees_columns: no sheet in {WORKBOOK} carries all of {COLUMNS}")
    return best


@criterion(description="the sheet is named Fees and the four columns stand in the stated order")
def fees_layout(workspace: Path) -> float:
    path = workspace / WORKBOOK
    for title, rows in _sheets(path):
        i = _header_index(rows)
        if i < 0:
            continue
        if not any(_filled(r) for r in rows[i + 1:]):
            continue
        header = [_norm(c) for c in rows[i]]
        named = 1.0 if _norm(title) == SHEET else 0.0
        first = 1.0 if i == 0 else 0.0
        placed = sum(
            1 for k, column in enumerate(COLUMNS)
            if k < len(header) and header[k] == column
        ) / len(COLUMNS)
        if named < 1.0:
            print(f"fees_layout: the run is written to sheet {title!r}; "
                  "section 10 names the worksheet Fees")
        if first < 1.0:
            print(f"fees_layout: the header row sits at row {i + 1}; "
                  "section 10 puts it in row 1")
        if placed < 1.0:
            print(f"fees_layout: the header reads {header!r}; section 10 fixes "
                  f"the column order as {COLUMNS}")
        return (named + first + placed) / 3.0
    print(f"fees_layout: no sheet in {WORKBOOK} carries all four column names "
          "over at least one data row")
    return 0.0


@criterion(description="one row per account, in the ascending order section 10 fixes")
def fees_row_order(workspace: Path) -> float:
    expected = _accounts(EXPECTED)
    if not expected:
        print(f"fees_row_order: {EXPECTED} carries no rows to compare against")
        return 0.0
    got = _accounts(workspace / WORKBOOK)
    if not got:
        print(f"fees_row_order: {WORKBOOK} carries no data rows")
        return 0.0
    hits = sum(1 for want, have in zip(expected, got) if want == have)
    if hits < len(expected):
        first = next(
            (i for i, (want, have) in enumerate(zip(expected, got)) if want != have),
            min(len(expected), len(got)),
        )
        want = expected[first] if first < len(expected) else "<past the last row>"
        have = got[first] if first < len(got) else "<row absent>"
        print(f"fees_row_order: {len(got)} rows against {len(expected)} expected; "
              f"row {first + 2} holds {have!r} where the ascending order puts {want!r}")
    return hits / max(len(expected), len(got))


def _populated(value) -> bool:
    """A leaf that carries something, or a container with at least one such leaf."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, dict):
        return any(_populated(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_populated(v) for v in value)
    return True


@criterion(description="workings.json parses and declares the keys the schedule sets out, populated")
def workings_keys(workspace: Path) -> float:
    path = workspace / "workings.json"
    if not path.exists():
        print("workings_keys: workings.json is absent")
        return 0.0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"workings_keys: {path.name} is not readable JSON: {type(exc).__name__}: {exc}")
        return 0.0
    if not isinstance(data, dict):
        print(f"workings_keys: {path.name} is a {type(data).__name__}, not a JSON object")
        return 0.0
    hits = 0
    for key in KEYS:
        if key not in data:
            print(f"workings_keys: {key} is absent")
        elif not _populated(data[key]):
            print(f"workings_keys: {key} is present but empty: {data[key]!r}")
        else:
            hits += 1
    return hits / len(KEYS)
