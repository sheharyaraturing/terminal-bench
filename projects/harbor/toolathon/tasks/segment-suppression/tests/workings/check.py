"""The workings file: the population accounting behind the figures.

Sixteen leaves, scored as a fraction, because they fail for different reasons and the
pattern of failure is the diagnosis. A run that gets the rates right but reports
`excluded.duplicate_visit_id = 0` never found the replayed rows; one that gets the
exclusions right but the rates wrong slipped on the arithmetic.
"""

import json
from pathlib import Path

from rewardkit import criterion

EXPECTED_DIR = Path("/tests/expected")
WORKINGS = "workings.json"

LEAVES = (
    ("metric",),
    ("period_start",),
    ("period_end",),
    ("rows_read",),
    ("eligible_visits",),
    ("excluded", "duplicate_visit_id"),
    ("excluded", "unknown_segment"),
    ("excluded", "outside_period"),
    ("excluded", "internal_channel"),
    ("excluded", "void_status"),
    ("segments_published",),
    ("segments_suppressed", "LOW_BASE"),
    ("segments_suppressed", "NO_BASE"),
    ("total_numerator",),
    ("total_denominator",),
    ("total_rate",),
)

_MISSING = object()


def _placeholder(blob) -> bool:
    """True when every figure in the workings file is still section 10's zero.

    Section 10 prints the schema with every figure set to 0 and says to replace each
    one. A file handed back with those zeros intact is the unfilled shape, and none of
    the leaves below are paid for it — three of them (`metric` and the two period
    dates) are otherwise copyable straight out of the document.
    """

    def numbers(node):
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            yield float(node)
        elif isinstance(node, dict):
            for value in node.values():
                yield from numbers(value)
        elif isinstance(node, list):
            for value in node:
                yield from numbers(value)

    found = list(numbers(blob))
    return bool(found) and all(value == 0.0 for value in found)


def _dig(blob, path):
    node = blob
    for step in path:
        if not isinstance(node, dict) or step not in node:
            return _MISSING
        node = node[step]
    return node


def _same(want, got) -> bool:
    if got is _MISSING or isinstance(got, bool):
        return False
    if isinstance(want, str):
        return isinstance(got, str) and got.strip() == want
    if isinstance(want, float):
        try:
            return abs(float(got) - want) <= 1e-6
        except (TypeError, ValueError):
            return False
    try:
        return float(got) == float(want) and float(got).is_integer()
    except (TypeError, ValueError):
        return False


@criterion(description="workings.json reports the population accounting correctly")
def workings_fields(workspace: Path) -> float:
    key_path = EXPECTED_DIR / WORKINGS
    try:
        expected = json.loads(key_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"workings_fields: the answer key is unreadable: {type(exc).__name__}: {exc}")
        return 0.0

    path = workspace / WORKINGS
    if not path.exists():
        return 0.0
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"workings_fields: {WORKINGS} is not readable JSON: {type(exc).__name__}: {exc}")
        return 0.0
    if not isinstance(blob, dict):
        return 0.0
    if _placeholder(blob):
        print(f"workings_fields: every figure in {WORKINGS} is still 0 — this is section 10's "
              "placeholder, not a workings file")
        return 0.0

    hits = 0
    for leaf in LEAVES:
        want = _dig(expected, leaf)
        got = _dig(blob, leaf)
        if _same(want, got):
            hits += 1
        else:
            shown = "absent" if got is _MISSING else repr(got)
            print(f"workings_fields: {'.'.join(leaf)} want {want!r} got {shown}")
    return hits / len(LEAVES)
