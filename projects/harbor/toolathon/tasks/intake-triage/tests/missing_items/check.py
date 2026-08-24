"""Fraction of in-scope forms whose outstanding items are listed exactly.

Exactly means: the same item codes, in the checklist's own order, and the two
sentinels spelled as the checklist spells them. Where a form has no list — nothing
outstanding, or completeness never assessed because the form contradicts itself —
an empty cell, a zero, a `None` and a row that is simply absent are all wrong, and
they are wrong in different ways, so `NONE` and `CONTRADICTION` are not
interchangeable either.
"""

from pathlib import Path

from rewardkit import criterion

EXPECTED = Path("/tests/expected/triage.xlsx")
HEADERS = ("formid", "status", "missingitems")
ABSENT = object()


def _norm_header(value) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "").replace("_", "")


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _column_letter(position: int) -> str:
    letter = ""
    position += 1
    while position:
        position, remainder = divmod(position - 1, 26)
        letter = chr(ord("A") + remainder) + letter
    return letter


def _tokens(raw: str) -> tuple[str, ...]:
    """Split a MissingItems cell into its listed codes, order preserved."""
    text = raw.replace(",", ";").replace("\n", ";").replace("|", ";")
    return tuple(part.strip().upper() for part in text.split(";") if part.strip())


def _read(path: Path, label: str) -> dict[str, tuple[str, ...]]:
    """FormID -> the MissingItems tokens, from whichever sheet carries the header.

    Loaded twice: `data_only=True` yields *cached* values and a workbook no
    spreadsheet application has ever opened has no cache, so a formula cell reads
    blank there. The formula-bearing load is the fallback, and a cell that proves
    to hold a formula is named as such rather than reported as an empty list.
    """
    import openpyxl

    if not path.exists():
        print(f"missing_items: {label} {path} does not exist")
        return {}
    try:
        cached = openpyxl.load_workbook(path, data_only=True)
    except Exception as exc:
        print(f"missing_items: could not open {label} {path}: {type(exc).__name__}: {exc}")
        return {}
    try:
        literal = openpyxl.load_workbook(path, data_only=False)
    except Exception:
        literal = None

    for name in cached.sheetnames:
        rows = list(cached[name].iter_rows(values_only=True))
        raws: list = []
        if literal is not None and name in literal.sheetnames:
            raws = list(literal[name].iter_rows(values_only=True))
        reported = [False]
        for top, row in enumerate(rows[:10]):
            if row is None:
                continue
            head = [_norm_header(c) for c in row]
            if not all(h in head for h in HEADERS):
                continue
            idx = {h: head.index(h) for h in HEADERS}
            out: dict[str, tuple[str, ...]] = {}
            for offset, data in enumerate(rows[top + 1:]):
                raw = raws[top + 1 + offset] if top + 1 + offset < len(raws) else ()
                data = data or ()
                raw = raw or ()
                # A row written entirely as formulas is blank in the cached read and
                # is still a row: it is skipped only when the literal read is empty too.
                if all(c is None for c in data) and all(c is None for c in raw):
                    continue

                def pick(column: str) -> str:
                    position = idx[column]
                    value = _cell(data[position]) if position < len(data) else ""
                    if value:
                        return value
                    fallback = _cell(raw[position]) if position < len(raw) else ""
                    if fallback.startswith("=") and not reported[0]:
                        reported[0] = True
                        coord = f"{_column_letter(position)}{top + 2 + offset}"
                        print(f"missing_items: {label} {name}!{coord} holds the formula "
                              f"{fallback!r} and no cached value; C.9 of the appendix "
                              "requires recorded values, not formulas")
                    return fallback

                form_id = pick("formid").upper()
                if form_id:
                    out[form_id] = _tokens(pick("missingitems"))
            return out

    print(f"missing_items: no sheet in {label} {path} has a "
          f"{list(HEADERS)} header; sheets were {cached.sheetnames}")
    return {}


@criterion(description="outstanding items listed exactly, in checklist order")
def missing_items(workspace: Path) -> float:
    expected = _read(EXPECTED, "expected")
    if not expected:
        return 0.0
    got = _read(workspace / "triage.xlsx", "produced")
    if not got:
        return 0.0
    hits = 0
    for form_id, want in expected.items():
        if got.get(form_id, ABSENT) == want:
            hits += 1
    return hits / max(len(expected), len(got))
