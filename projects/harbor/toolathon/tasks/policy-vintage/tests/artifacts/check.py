"""The decision register appeared, on the sheet the manual names, with its columns
in the order the manual states, and carrying decided lines.

Structure only: whether the file is there and shaped right, never whether the
decisions in it are correct. A register full of rows with the wrong verdicts scores
here and scores badly elsewhere, which is the split that separates "did it wrong"
from "did nothing".

Nothing here pays out for a headers-only shell. Every criterion is gated on the
sheet carrying at least one data row, so an agent that writes the five headers and
stops banks nothing: manual 6.4 asks for "one row for every line in claims.xlsx",
and zero rows is not a partial answer to that.

Every criterion is also scaled by _completeness(): the fraction of the expected
37 rows actually present, capped at 1.0. A file that is shaped perfectly but
carries only one or two invented rows is not "structurally correct" in any
sense manual 6.4 would recognise — without this, a single fabricated row
satisfied every criterion below in full, and register_populated's own gate
(0 rows -> 0) was the only place row *count* otherwise mattered.
"""

from pathlib import Path

from rewardkit import criterion

# Manual 6.4: "The columns are Claim, Line, VersionApplied, Verdict and Reason,
# in that order and under those names." The tuple carries both facts — membership
# is scored by required_columns, position by column_order.
REQUIRED = ("claim", "line", "versionapplied", "verdict", "reason")

EXPECTED = Path("/tests/expected/decisions.xlsx")
SPEC = "AP_Expense_Manual.docx 6.4"


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
    cached results, so on the cached pass a register written entirely in formulas
    looks like a header and nothing else; the second pass sees the formula text and
    counts the rows that are really there. The richer of the two passes wins.
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
    """Sheets that look like the register and are not empty."""
    return [s for s in _sheets(path) if s.names and s.rows > 0]


def _expected_rows() -> int:
    """How many rows the answer key carries, for _completeness() below.

    Counted over _registers(), not _sheets(): an unrelated sheet in the answer
    key (or, symmetrically, one fabricated into the workspace file) must never
    move this number.
    """
    return max((s.rows for s in _registers(EXPECTED)), default=0)


def _completeness(workspace: Path) -> float:
    """Rows actually present as a fraction of the rows the manual covers, capped at 1.0.

    Without this, a single fabricated row satisfies every criterion below in
    full — manual 6.4 asks for "one row for every line in claims.xlsx", not
    for at least one row that happens to look right, and register_populated's
    own gate (0 rows -> 0) is the only place row *count* otherwise mattered.

    Both sides are counted over _registers(), which only counts sheets that
    carry a recognisable header — otherwise a fabricated row on Decisions plus
    an arbitrary block of rows on some unrelated sheet (e.g. Notes) would
    inflate the produced count via _sheets() without inflating the expected
    count the same way, restoring full completeness for no real work.
    """
    expected = _expected_rows()
    if expected == 0:
        print(f"artifacts: could not read a row count from the expected register at "
              f"{EXPECTED}; completeness cannot be computed against it")
        return 0.0
    got = max((s.rows for s in _registers(workspace / "decisions.xlsx")), default=0)
    return min(got / expected, 1.0)


KEY = ("claim", "line")


def _row_keys(path: Path) -> tuple[list[tuple], str] | None:
    """(Claim, Line) for every populated data row on the register with the most rows.

    Same double-read strategy as _sheets: a workbook nobody opened in Excel carries no
    cached formula results, so the cached pass and the raw pass are merged and the
    richer of the two wins, keeping this consistent with what register_populated counts.
    """
    import openpyxl

    if not path.exists():
        return None
    best: tuple[list[tuple], str] | None = None
    for cached in (True, False):
        try:
            book = openpyxl.load_workbook(path, data_only=cached)
        except Exception:
            continue
        for sheet in book.worksheets:
            grid = [tuple(cell.value for cell in row) for row in sheet.iter_rows()]
            names, start = _header_row(grid)
            idx = {c: names.index(c) for c in KEY if c in names}
            if len(idx) < len(KEY):
                continue
            keys = [tuple(_label(row[idx[c]]) for c in KEY)
                    for row in grid[start:] if _populated(row)]
            if best is None or len(keys) > len(best[0]):
                best = (keys, sheet.title)
    return best 


@criterion(description="no two rows in decisions.xlsx name the same Claim and Line")
def no_duplicate_rows(workspace: Path) -> float:
    found = _row_keys(workspace / "decisions.xlsx")
    if not found or not found[0]:
        return 0.0
    keys, title = found
    uniques = len(set(keys))
    if uniques == len(keys):
        return 1.0 * _completeness(workspace)
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    print(f"artifacts: {title} repeats Claim/Line {dupes[:3]} across more than one row; "
          f"{SPEC} asks for one row for every line in claims.xlsx, and no others")
    return (uniques / len(keys)) * _completeness(workspace)


@criterion(description="decisions.xlsx exists and carries at least one decided line")
def register_populated(workspace: Path) -> float:
    path = workspace / "decisions.xlsx"
    if not path.exists():
        print("artifacts: decisions.xlsx is not in the workspace root")
        return 0.0
    sheets = _sheets(path)
    live = [s for s in sheets if s.names and s.rows > 0]
    if not live:
        if any(s.names for s in sheets):
            print("artifacts: decisions.xlsx carries a header row and no decided lines; "
                  f"{SPEC} asks for one row for every line in claims.xlsx")
        else:
            print("artifacts: no sheet in decisions.xlsx has a recognisable header row")
        return 0.0
    # One line per affected sheet, naming a cell, so a failed run is debuggable.
    for sheet in live:
        if sheet.formula is not None:
            coord, value = sheet.formula
            print(f"artifacts: {sheet.title}!{coord} holds the formula {value!r} and no "
                  f"cached value; {SPEC} requires recorded values, not formulas")
    completeness = _completeness(workspace)
    if completeness < 1.0:
        got = max((s.rows for s in live), default=0)
        print(f"artifacts: decisions.xlsx carries {got} of {_expected_rows()} "
              f"expected rows; {SPEC} asks for one row for every line in claims.xlsx")
    return completeness


@criterion(description="decisions.xlsx carries the five columns the manual specifies")
def required_columns(workspace: Path) -> float:
    raw = max((sum(1 for c in REQUIRED if c in s.names) / len(REQUIRED)
               for s in _registers(workspace / "decisions.xlsx")), default=0.0)
    return raw * _completeness(workspace)


@criterion(description="the five columns sit in the order the manual states")
def column_order(workspace: Path) -> float:
    """Fraction of the five columns standing in their stated position.

    Fractional, not boolean: a register that swaps Verdict and Reason has three of
    the five columns where the manual puts them, and reads differently from one
    whose header is shuffled outright.
    """
    best, shown = 0.0, None
    for sheet in _registers(workspace / "decisions.xlsx"):
        hits = sum(1 for position, want in enumerate(REQUIRED)
                   if position < len(sheet.names) and sheet.names[position] == want)
        if hits / len(REQUIRED) > best or shown is None:
            shown = sheet
        best = max(best, hits / len(REQUIRED))
    if shown is not None and best < 1.0:
        print(f"artifacts: {shown.title} reads {shown.names}; {SPEC} states the column "
              f"order {list(REQUIRED)}")
    return best * _completeness(workspace)


@criterion(description="the decisions sit on a worksheet named Decisions")
def sheet_named(workspace: Path) -> float:
    sheets = _registers(workspace / "decisions.xlsx")
    for sheet in sheets:
        if sheet.title.strip().lower() == "decisions":
            return 1.0 * _completeness(workspace)
    if sheets:
        print("artifacts: no worksheet named 'Decisions' carries decided lines; "
              f"found {[s.title for s in sheets]}")
    return 0.0
