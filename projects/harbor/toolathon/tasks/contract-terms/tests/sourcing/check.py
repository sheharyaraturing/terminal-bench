"""Fraction of in-scope invoices naming the document and clause that governed.

Graded separately from the due date because they are independent failures: an
agent can reach the right date from the wrong document (30 days from the manual
where a contract happens to say 30), and it can identify the right contract and
still miscount the days. Scoring only the date would pay for the first of those.

Rows the agent invented enlarge the denominator, so padding cannot lift the score.
For the two invoices clause 6.1 leaves unresolved the expected value is the
reason code, and None, "", 0 and an absent row each normalise to something that
is not that code.
"""

from __future__ import annotations

import re
from pathlib import Path

from rewardkit import criterion

EXPECTED = Path("/tests/expected/payment_schedule.xlsx")
ARTIFACT = "payment_schedule.xlsx"
REQUIRED = ("invoice", "vendor", "duedate", "governingsource")


def _key(cell) -> str:
    return "" if cell is None else str(cell).strip().upper()


def _norm_src(value) -> str:
    text = "" if value is None else str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text.rstrip(".").upper()


# The reason code is a value, not an absence; guard against conflating the two.
assert _norm_src(None) != "REVIEW-CONFLICTING-TERMS"
assert _norm_src("") != "REVIEW-CONFLICTING-TERMS"
assert _norm_src(0) != "REVIEW-CONFLICTING-TERMS"
assert _norm_src("review-conflicting-terms") == "REVIEW-CONFLICTING-TERMS"


def _unwrap_formula(text: str) -> str:
    body = text.lstrip("=").strip()
    if len(body) >= 2 and body[0] == body[-1] and body[0] in "\"'":
        return body[1:-1]
    return text


def _sources(path: Path, label: str) -> tuple[dict[str, str], int]:
    import openpyxl

    if not path.exists():
        print(f"sourcing: {label} {path.name} is missing")
        return {}, 0
    try:
        values = openpyxl.load_workbook(path, data_only=True)
    except Exception as exc:
        print(f"sourcing: could not open {label} {path.name}: {type(exc).__name__}: {exc}")
        return {}, 0
    try:
        # data_only=True yields cached results only; a program-written workbook has
        # none, so a formula cell reads None. Keep a formula-bearing copy to report.
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
            raw_src = sheet.cell(row=r, column=columns["governingsource"]).value
            if raw_key is None and raw_src is None:
                continue
            if raw_src is None and mirror is not None:
                shadow = mirror.cell(row=r, column=columns["governingsource"]).value
                if isinstance(shadow, str) and shadow.startswith("="):
                    held.append((sheet.cell(row=r, column=columns["governingsource"]).coordinate, shadow))
                    raw_src = _unwrap_formula(shadow)
            rows += 1
            key = _key(raw_key)
            if key:
                out[key] = _norm_src(raw_src)
        if held:
            coord, formula = held[0]
            extra = f" ({len(held)} such cells on this sheet)" if len(held) > 1 else ""
            print(
                f"sourcing: {label} {sheet.title}!{coord} holds the formula {formula!r} and no "
                f"cached value; AP manual clause 7.6 requires recorded values, not formulas{extra}"
            )
        return out, rows

    print(f"sourcing: no sheet in {label} {path.name} carries all of {REQUIRED}")
    return {}, 0


@criterion(description="in-scope invoices name the governing document and clause")
def governing_source(workspace: Path) -> float:
    expected, _ = _sources(EXPECTED, "expected")
    if not expected:
        return 0.0
    got, rows = _sources(workspace / ARTIFACT, "agent")
    hits = sum(1 for ref, src in expected.items() if got.get(ref, "") == src)
    misses = [ref for ref, src in expected.items() if got.get(ref, "") != src]
    if misses:
        print(f"sourcing: {len(misses)} wrong or missing, first few {misses[:5]}")
    return hits / max(len(expected), rows, 1)
