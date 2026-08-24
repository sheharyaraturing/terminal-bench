"""The routing log appeared, on the sheet the manual names, with its columns in
the order the manual states, and carrying routed rows.

Structure only: whether the file is there and shaped right, never whether the
routing in it is correct. A log full of rows with the wrong approver scores
here and scores badly on the routing dimension, which is the split that
separates "did it wrong" from "did nothing".

Nothing here pays out for a headers-only shell. Every criterion is gated on
the sheet carrying at least one data row: manual 7.7 asks for "one row for
every requisition the cycle covers", and zero rows is not a partial answer to
that.
"""

from pathlib import Path

from rewardkit import criterion

# Manual 7.7: "The first row of that sheet carries the headings Ref, Approver
# and Band, in that order." Membership is scored by required_columns, position
# by column_order.
REQUIRED = ("ref", "approver", "band")

SPEC = "Finance_Manual.docx 7.7"


def _label(value) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "").replace("_", "")


def _header_row(rows: list[tuple]) -> tuple[list[str], int]:
    """The first row in the first five that names at least two required columns."""
    for index, row in enumerate(rows[:5]):
        if row is None:
            continue
        names = [_label(c) for c in row]
        if sum(1 for c in REQUIRED if c in names) >= 2:
            return names, index + 1
    return [], 0


def _populated(row) -> bool:
    return bool(row) and any(c is not None and str(c).strip() != "" for c in row)


class Sheet:
    __slots__ = ("title", "names", "rows", "formula")

    def __init__(self, title: str, names: list[str], rows: int, formula) -> None:
        self.title, self.names, self.rows, self.formula = title, names, rows, formula


def _sheets(path: Path) -> list[Sheet]:
    """One Sheet per worksheet: header names, data-row count, first raw formula.

    Read twice. A workbook a program wrote without ever running Excel carries no
    cached results, so on the cached pass a log written entirely in formulas
    looks like a header and nothing else; the second pass sees the formula text
    and counts the rows that are really there. The richer of the two passes
    wins.
    """
    import openpyxl

    best: dict[str, Sheet] = {}
    if not path.exists():
        return []
    for cached in (True, False):
        try:
            book = openpyxl.load_workbook(path, data_only=cached)
        except Exception as exc:
            print(f"artifacts: could not read {path}: {type(exc).__name__}: {exc}")
            continue
        for sheet in book.worksheets:
            grid = [list(row) for row in sheet.iter_rows()]
            values = [tuple(cell.value for cell in row) for row in grid]
            names, start = _header_row(values)
            rows = 0
            formula = None
            for cells, row in zip(grid[start:], values[start:]):
                if not _populated(row):
                    continue
                rows += 1
                if formula is None:
                    for cell in cells:
                        if isinstance(cell.value, str) and cell.value.startswith("="):
                            formula = (cell.coordinate, cell.value)
                            break
            found = Sheet(sheet.title, names, rows, formula)
            prior = best.get(sheet.title)
            if prior is None or (found.rows, len(found.names)) > (prior.rows, len(prior.names)):
                best[sheet.title] = found
            elif prior.formula is None and formula is not None:
                prior.formula = formula
    return list(best.values())


def _registers(path: Path) -> list[Sheet]:
    """Sheets that look like the routing log and are not empty."""
    return [s for s in _sheets(path) if s.names and s.rows > 0]


@criterion(description="routing_log.xlsx exists and carries at least one routed row")
def register_populated(workspace: Path) -> float:
    path = workspace / "routing_log.xlsx"
    if not path.exists():
        print("artifacts: routing_log.xlsx is not in the workspace root")
        return 0.0
    sheets = _sheets(path)
    live = [s for s in sheets if s.names and s.rows > 0]
    if not live:
        if any(s.names for s in sheets):
            print("artifacts: routing_log.xlsx carries a header row and no routed rows; "
                  f"{SPEC} asks for one row for every requisition the cycle covers")
        else:
            print("artifacts: no sheet in routing_log.xlsx has a recognisable header row")
        return 0.0
    for sheet in live:
        if sheet.formula is not None:
            coord, value = sheet.formula
            print(f"artifacts: {sheet.title}!{coord} holds the formula {value!r} and no "
                  f"cached value; {SPEC} requires literal values, not formulas")
    return 1.0


@criterion(description="routing_log.xlsx carries the Ref, Approver and Band columns")
def required_columns(workspace: Path) -> float:
    return max((sum(1 for c in REQUIRED if c in s.names) / len(REQUIRED)
                for s in _registers(workspace / "routing_log.xlsx")), default=0.0)


@criterion(description="the three columns sit in the order the manual states")
def column_order(workspace: Path) -> float:
    """Fraction of the three columns standing in their stated position.

    Fractional, not boolean: a log that swaps Approver and Band has one of the
    three columns out of place, and reads differently from one whose header is
    shuffled outright.
    """
    best, shown = 0.0, None
    for sheet in _registers(workspace / "routing_log.xlsx"):
        hits = sum(1 for position, want in enumerate(REQUIRED)
                   if position < len(sheet.names) and sheet.names[position] == want)
        if hits / len(REQUIRED) > best or shown is None:
            shown = sheet
        best = max(best, hits / len(REQUIRED))
    if shown is not None and best < 1.0:
        print(f"artifacts: {shown.title} reads {shown.names}; {SPEC} states the column "
              f"order {list(REQUIRED)}")
    return best


@criterion(description="the routing sits on a worksheet named Routing")
def sheet_named(workspace: Path) -> float:
    sheets = _registers(workspace / "routing_log.xlsx")
    for sheet in sheets:
        if sheet.title.strip().lower() == "routing":
            return 1.0
    if sheets:
        print("artifacts: no worksheet named 'Routing' carries routed rows; "
              f"found {[s.title for s in sheets]}")
    return 0.0
