"""Fraction of claim lines carrying the verdict and reason the manual produces.

Verdict and Reason are scored together, half a point each, so a line rejected for
the right cause reads differently from one rejected for the wrong one. The receipt
test runs before the ceiling test and both thresholds move between policy versions,
so this dimension separates an agent that read the governing version's own figures
from one that reused the last table it saw.

Extra rows the agent invented count against the denominator. A blank, zero or
missing cell is never a hit, which is what rejects the four usual near-misses for
the held line: 0, the empty string, null, and no row at all.
"""

import re
from pathlib import Path

from rewardkit import criterion

EXPECTED = Path("/tests/expected/decisions.xlsx")
FIELDS = ("verdict", "reason")
DIM = "disposition"
SPEC = "AP_Expense_Manual.docx 6.4"


def _norm(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _label(name) -> str:
    return _norm(name).lower().replace(" ", "").replace("_", "")


_STRING = re.compile(r'"([^"]*)"')


def _unwrap(formula: str):
    """A formula whose whole body is literal text or a literal number, unwrapped.

    `="v3"`, `=1`, `="v"&"3"` and `=CONCATENATE("v","3")` each name a value that
    can be graded. A formula that reaches for a cell or a function returns None,
    and the caller reports the formula rather than guessing at what it would
    have evaluated to.
    """
    body = formula[1:].strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", body):
        return _norm(float(body))
    literals = _STRING.findall(body)
    if not literals:
        return None
    residue = re.sub(r"(?i)\bCONCATENATE?\b", "", _STRING.sub("", body))
    if residue.strip(" &,+()"):
        return None
    return "".join(literals)


def _key(cells, position, unreadable: list[str]) -> str:
    """Claim and Line join the agent's rows to the key, so they are unwrapped too.

    An agent that writes the whole register as formulas has a correct answer with
    no cached values; leaving the join columns raw would fail every row of it.
    """
    if position is None or position >= len(cells):
        return ""
    cell = cells[position]
    text = _norm(cell.value)
    if not text.startswith("="):
        return text
    literal = _unwrap(text)
    if literal is None:
        # Unresolvable, so it can never match a key — but it stays in the map, and
        # therefore in the denominator, rather than becoming a free padding row.
        unreadable.append(f"{cell.coordinate} {text!r}")
        return text
    return literal


def _scan(book, wanted: tuple[str, ...]) -> dict:
    """(claim, line) -> field -> (value, sheet title, cell coordinate).

    The coordinate is carried so a failure can be reported against the cell that
    caused it rather than against a phantom blank.
    """
    out: dict[tuple[str, str], dict[str, tuple[str, str, str]]] = {}
    unreadable: list[str] = []
    for sheet in book.worksheets:
        grid = [list(row) for row in sheet.iter_rows()]
        values = [tuple(cell.value for cell in row) for row in grid]
        header = None
        start = 0
        for index, row in enumerate(values[:5]):
            if row is None:
                continue
            names = [_label(c) for c in row]
            if "claim" in names and "line" in names and any(w in names for w in wanted):
                header, start = names, index + 1
                break
        if header is None:
            continue
        idx = {name: header.index(name)
               for name in ("claim", "line", *wanted) if name in header}
        for cells, row in zip(grid[start:], values[start:]):
            if row is None or all(c is None for c in row):
                continue
            claim = _key(cells, idx.get("claim"), unreadable)
            line = _key(cells, idx.get("line"), unreadable)
            if not claim or not line:
                continue
            record = out.setdefault((claim.upper(), line), {})
            for name in wanted:
                position = idx.get(name)
                if position is not None and position < len(cells):
                    cell = cells[position]
                    record.setdefault(
                        name, (_norm(cell.value), sheet.title, cell.coordinate))
    if unreadable:
        print(f"{DIM}: {len(unreadable)} row(s) name their Claim or Line with a formula "
              f"the grader cannot resolve, e.g. {unreadable[0]}; those rows cannot be "
              "matched to a claim line at all")
    return out


def _read(path: Path, wanted: tuple[str, ...]) -> dict[tuple[str, str], dict[str, str]]:
    """Cached values first, formulas second. A workbook written by a program that
    never ran Excel has no cached values, so every formula cell reads blank on the
    first pass; the second pass recovers what the agent actually wrote.

    A formula with no cached result is reported against its own sheet and cell, once
    per sheet, so a register written wholly in formulas names the cause in one line
    instead of flooding the log with a hundred of them.
    """
    import openpyxl

    if not path.exists():
        return {}
    passes = []
    for cached in (True, False):
        try:
            passes.append(_scan(openpyxl.load_workbook(path, data_only=cached), wanted))
        except Exception as exc:
            print(f"{DIM}: could not read {path}: {type(exc).__name__}: {exc}")
            return {}
    merged, fallback = passes
    unwrapped: set[str] = set()
    stranded: set[str] = set()
    for key, record in fallback.items():
        target = merged.setdefault(key, {})
        for name, (value, title, coord) in record.items():
            prior = target.get(name)
            if prior is not None and prior[0]:
                continue
            if value.startswith("="):
                literal = _unwrap(value)
                if literal is not None:
                    if title not in unwrapped:
                        unwrapped.add(title)
                        print(f"{DIM}: {title}!{coord} was written as the formula "
                              f"{value!r} with no cached value; grading the literal "
                              f"{literal!r} it wraps, and likewise elsewhere on "
                              f"{title}")
                    value = literal
                elif title not in stranded:
                    stranded.add(title)
                    print(f"{DIM}: {title}!{coord} holds the formula {value!r} and no "
                          f"cached value; {SPEC} requires recorded values, not formulas")
            target[name] = (value, title, coord)
    return {key: {name: cell[0] for name, cell in record.items()}
            for key, record in merged.items()}


@criterion(description="claim lines carrying the verdict and the reason code the manual produces")
def disposition(workspace: Path) -> float:
    expected = _read(EXPECTED, FIELDS)
    if not expected:
        print(f"disposition: answer key {EXPECTED} is unreadable or empty")
        return 0.0
    got = _read(workspace / "decisions.xlsx", FIELDS)

    hits = 0.0
    for key, record in expected.items():
        mine = got.get(key, {})
        for name in FIELDS:
            want = record.get(name, "")
            value = mine.get(name, "")
            if value and value.casefold() == want.casefold():
                hits += 1.0 / len(FIELDS)
    return hits / max(len(expected), len(got), 1)
