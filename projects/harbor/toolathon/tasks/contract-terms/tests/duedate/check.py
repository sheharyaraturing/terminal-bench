"""Fraction of in-scope invoices carrying the due date the manual produces.

Partial work scores: 20 of 25 dates right reads 0.80, not 0. Rows the agent
invented, and duplicated invoice numbers, enlarge the denominator, so padding the
sheet cannot lift the score; an agent that produced nothing reads 0.

Two invoices are unresolvable under clause 6.1 and their due date is the literal
`REVIEW`. Normalisation deliberately maps None, "", 0 and a missing row to
distinct non-REVIEW strings, so all four near-miss forms of "undefined" score as
misses rather than as the flag.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from rewardkit import criterion

EXPECTED = Path("/tests/expected/payment_schedule.xlsx")
ARTIFACT = "payment_schedule.xlsx"
REQUIRED = ("invoice", "vendor", "duedate", "governingsource")


def _key(cell) -> str:
    return "" if cell is None else str(cell).strip().upper()


def _norm_due(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:[ T]\d{2}:\d{2}(?::\d{2})?)?$", text)
    if match:
        return match.group(1)
    return text.upper()


# A blank, a zero, an empty string and an absent row are four different things and
# none of them is the flag. Guard the normaliser against ever conflating them.
assert _norm_due(None) != "REVIEW"
assert _norm_due("") != "REVIEW"
assert _norm_due(0) != "REVIEW"
assert _norm_due("REVIEW") == "REVIEW"


def _unwrap_formula(text: str) -> str:
    """A formula cell that is really a literal, e.g. ="2026-02-09"."""
    body = text.lstrip("=").strip()
    if len(body) >= 2 and body[0] == body[-1] and body[0] in "\"'":
        return body[1:-1]
    return text


def _schedule(path: Path, label: str) -> tuple[dict[str, str], int]:
    """Due date per invoice, plus the number of data rows written."""
    import openpyxl

    if not path.exists():
        print(f"duedate: {label} {path.name} is missing")
        return {}, 0
    try:
        values = openpyxl.load_workbook(path, data_only=True)
    except Exception as exc:
        print(f"duedate: could not open {label} {path.name}: {type(exc).__name__}: {exc}")
        return {}, 0
    try:
        # data_only=True returns *cached* results; a workbook written by a program
        # Excel never opened has no cache, so formula cells read None. The second
        # load keeps the formulas so those cells are reported, not silently zeroed.
        formulas = openpyxl.load_workbook(path, data_only=False)
    except Exception:
        formulas = None

    for sheet in values.worksheets:
        head_row = None
        columns: dict[str, int] = {}
        for row in sheet.iter_rows(min_row=1, max_row=10):
            names: dict[str, int] = {}
            for cell in row:
                if cell.value is None:
                    continue
                name = str(cell.value).strip().lower().replace(" ", "").replace("_", "")
                if name in REQUIRED and name not in names:
                    names[name] = cell.column
            if all(c in names for c in REQUIRED):
                head_row, columns = row[0].row, names
                break
        if head_row is None:
            continue

        mirror = None
        if formulas is not None and sheet.title in formulas.sheetnames:
            mirror = formulas[sheet.title]

        out: dict[str, str] = {}
        rows = 0
        held: list[tuple[str, str]] = []
        for r in range(head_row + 1, sheet.max_row + 1):
            raw_key = sheet.cell(row=r, column=columns["invoice"]).value
            raw_due = sheet.cell(row=r, column=columns["duedate"]).value
            if raw_key is None and raw_due is None:
                continue
            if raw_due is None and mirror is not None:
                shadow = mirror.cell(row=r, column=columns["duedate"]).value
                if isinstance(shadow, str) and shadow.startswith("="):
                    held.append((sheet.cell(row=r, column=columns["duedate"]).coordinate, shadow))
                    raw_due = _unwrap_formula(shadow)
            rows += 1
            key = _key(raw_key)
            if key:
                out[key] = _norm_due(raw_due)
        if held:
            coord, formula = held[0]
            extra = f" ({len(held)} such cells on this sheet)" if len(held) > 1 else ""
            print(
                f"duedate: {label} {sheet.title}!{coord} holds the formula {formula!r} and no "
                f"cached value; AP manual clause 7.6 requires recorded values, not formulas{extra}"
            )
        return out, rows

    print(f"duedate: no sheet in {label} {path.name} carries all of {REQUIRED}")
    return {}, 0


@criterion(description="in-scope invoices carry the due date the AP manual produces")
def due_dates(workspace: Path) -> float:
    expected, _ = _schedule(EXPECTED, "expected")
    if not expected:
        return 0.0
    got, rows = _schedule(workspace / ARTIFACT, "agent")
    hits = sum(1 for ref, due in expected.items() if got.get(ref, "") == due)
    misses = [ref for ref, due in expected.items() if got.get(ref, "") != due]
    if misses:
        print(f"duedate: {len(misses)} wrong or missing, first few {misses[:5]}")
    return hits / max(len(expected), rows, 1)
