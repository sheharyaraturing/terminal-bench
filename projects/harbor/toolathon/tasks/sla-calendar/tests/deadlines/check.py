"""Fraction of tickets whose severity and response deadline are recorded correctly.

Both columns are graded, because a column the instruction demands and the grader
ignores is a column an agent can fill with anything.

Every fraction divides by max(len(expected), len(got)), so inventing rows — the
decommissioned queue is the obvious way to do it — costs score instead of adding
it, and an agent that writes nothing reads 0.
"""

from datetime import datetime
from pathlib import Path

import rewardkit as rk
from rewardkit import criterion

EXPECTED = Path("/tests/expected/sla_report.xlsx")
REQUIRED = ("ticket", "severity", "deadline", "breached")
SENTINEL = "UNDETERMINED"
FORMULA = "<spreadsheet formula, no stored value>"


def _cell(value) -> str:
    """One agent-written cell as comparable text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _read(path: Path, label: str) -> dict[str, dict[str, str]]:
    """Rows keyed by ticket, taken from whichever sheet carries the header.

    The workbook is loaded twice. `data_only=True` returns cached formula results,
    and a workbook written by a program that never ran Excel has no cache, so every
    formula cell would otherwise read blank. The second, formula-bearing load lets
    a formula be reported as a formula rather than misdiagnosed as an empty cell,
    and the first such cell is named by sheet and coordinate so whoever debugs the
    run is not sent after a phantom blank.
    """
    import openpyxl
    from openpyxl.utils import get_column_letter

    if not path.exists():
        print(f"{label}: {path.name} does not exist")
        return {}
    try:
        cached = openpyxl.load_workbook(path, data_only=True)
    except Exception as exc:
        print(f"{label}: could not open {path.name}: {type(exc).__name__}: {exc}")
        return {}
    try:
        literal = openpyxl.load_workbook(path, data_only=False)
    except Exception:
        literal = None

    for name in cached.sheetnames:
        rows = [list(r) for r in cached[name].iter_rows(values_only=True)]
        if not rows:
            continue
        header = [_cell(c).lower() for c in rows[0]]
        if any(col not in header for col in REQUIRED):
            continue
        raw = []
        if literal is not None and name in literal.sheetnames:
            raw = [list(r) for r in literal[name].iter_rows(values_only=True)]

        idx = {col: header.index(col) for col in REQUIRED}
        out: dict[str, dict[str, str]] = {}
        formulas = 0
        first_formula: tuple[str, str] | None = None
        for i, row in enumerate(rows[1:], start=1):
            if not row or all(c is None for c in row):
                continue
            record = {}
            for col, j in idx.items():
                value = row[j] if j < len(row) else None
                if value is None and i < len(raw) and j < len(raw[i]):
                    alt = raw[i][j]
                    if isinstance(alt, str) and alt.startswith("="):
                        if first_formula is None:
                            # iter_rows starts at A1, so data row i is sheet row i+1
                            first_formula = (f"{get_column_letter(j + 1)}{i + 1}", alt)
                        value, formulas = FORMULA, formulas + 1
                    elif alt is not None:
                        value = alt
                record[col] = _cell(value)
            ticket = record["ticket"].upper()
            if ticket:
                out[ticket] = record
        if first_formula is not None:
            # one line per affected sheet, not per cell: a wholly formula-written
            # answer should name its cause once rather than flood the log
            coord, expr = first_formula
            print(f"{label}: {name}!{coord} holds the formula {expr!r} and no cached "
                  f"value; SOP section 11 requires recorded values, not formulas "
                  f"({formulas} such cell(s) in this sheet)")
        return out

    print(f"{label}: no sheet in {path.name} carries all of {REQUIRED}; "
          f"sheets are {cached.sheetnames}")
    return {}


def _pair(workspace: Path):
    return _read(EXPECTED, "expected"), _read(workspace / "sla_report.xlsx", "report")


@criterion(description="each ticket's severity code is recorded as the SOP normalises it")
def severity(workspace: Path) -> float:
    """Compared as written, not case-folded: SOP section 11 says the code is recorded
    trimmed and upper-cased, so a raw ` s3 ` copied out of the export is a miss."""
    want, got = _pair(workspace)
    if not want:
        return 0.0
    hits = 0
    misses: list[str] = []
    for ticket, row in want.items():
        mine = got.get(ticket, {}).get("severity", "")
        if mine == row["severity"]:
            hits += 1
        elif len(misses) < 6:
            misses.append(f"{ticket}: wanted {row['severity']!r}, got {mine!r}")
    if misses:
        print("severity: " + "; ".join(misses))
    return hits / max(len(want), len(got))


@criterion(description="each ticket's response deadline matches the business-hour clock")
def deadline(workspace: Path) -> float:
    want, got = _pair(workspace)
    if not want:
        return 0.0
    hits = 0
    misses: list[str] = []
    for ticket, row in want.items():
        mine = got.get(ticket, {}).get("deadline", "")
        if mine.upper() == row["deadline"].upper():
            hits += 1
        elif len(misses) < 6:
            misses.append(f"{ticket}: wanted {row['deadline']!r}, got {mine!r}")
    if misses:
        print("deadline: " + "; ".join(misses))
    return hits / max(len(want), len(got))


@criterion(description="tickets with no computable deadline carry the UNDETERMINED sentinel")
def undetermined(workspace: Path) -> float:
    """0, an empty cell, null and a dropped row are each a wrong answer here, not
    a partially right one, so the comparison is against the literal sentinel."""
    want, got = _pair(workspace)
    blanks = {k: v for k, v in want.items() if v["deadline"].upper() == SENTINEL}
    if not blanks:
        return 0.0
    hits = 0
    for ticket in blanks:
        row = got.get(ticket)
        if row is None:
            print(f"undetermined: {ticket} is missing from the report entirely")
            continue
        if row["deadline"].upper() == SENTINEL and row["breached"].upper() == SENTINEL:
            hits += 1
        else:
            print(f"undetermined: {ticket} reads deadline={row['deadline']!r} "
                  f"breached={row['breached']!r}, wanted {SENTINEL} in both")
    return hits / len(blanks)


@criterion(
    description="report rows sit in ascending Ticket order, as SOP section 11 states",
    shared=True,
)
def row_order(workspace: Path) -> float:
    """The SOP states a row order, so the row order is measured — positionally, and as
    a fraction of rows that sit where they belong rather than as a pass/fail flag."""
    want, got = _pair(workspace)
    if not want:
        return 0.0
    wanted, mine = list(want), list(got)
    hits = sum(1 for i, ticket in enumerate(wanted) if i < len(mine) and mine[i] == ticket)
    if hits < max(len(wanted), len(mine)):
        for i, ticket in enumerate(wanted):
            if i >= len(mine) or mine[i] != ticket:
                print(f"row_order: row {i + 2} of the sheet reads "
                      f"{(mine[i] if i < len(mine) else '(no row)')!r}, "
                      f"wanted {ticket!r}; {hits} of {max(len(wanted), len(mine))} "
                      "rows sit in ascending Ticket order")
                break
    return hits / max(len(wanted), len(mine))


rk.row_order(weight=0.5)
