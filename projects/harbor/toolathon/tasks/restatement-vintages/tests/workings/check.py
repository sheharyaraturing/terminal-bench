"""Fraction of the record accounting in workings.json that matches the key.

The accounting is what makes an accidentally-right figure hard: a wrong population
lands on the right total far more often than it lands on the right total AND the
right five exclusion counts. Each key scores independently, so a model that got the
figure wrong but the exclusions right reads differently from one that got neither.
"""

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from rewardkit import criterion

EXPECTED = Path("/tests/expected/workings.json")

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

MISSING = object()

# The five constants above — metric, reporting_cutoff, undefined, undefined_reason
# and denominator — are printed verbatim in the policy, so a file that copies the
# skeleton and counts nothing would bank them for free. Nothing scores until the
# accounting accounts for something.
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


def _dig(payload, path_keys):
    node = payload
    for key in path_keys:
        if not isinstance(node, dict) or key not in node:
            return MISSING
        node = node[key]
    return node


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value.replace(",", "").replace("$", "").strip())
        except (InvalidOperation, ValueError):
            return None
    return None


def _match(got, want) -> bool:
    if got is MISSING:
        return False
    if want is None:
        # The policy fixes these as JSON null. 0, "" and an absent key are not null.
        return got is None
    if isinstance(want, bool):
        return isinstance(got, bool) and got == want
    if isinstance(want, str):
        return isinstance(got, str) and got.strip() == want
    left, right = _number(got), _number(want)
    return left is not None and left == right


@criterion(description="workings.json matches the record accounting the policy requires")
def workings(workspace: Path) -> float:
    try:
        want = json.loads(EXPECTED.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"workings: the answer key at {EXPECTED} did not read: "
              f"{type(exc).__name__}: {exc}")
        return 0.0

    path = workspace / "workings.json"
    if not path.exists():
        return 0.0
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"workings: workings.json is not valid JSON: {type(exc).__name__}: {exc}")
        return 0.0

    counted = Decimal(0)
    for path_keys in COUNT_KEYS:
        value = _number(_dig(got, path_keys))
        if value is not None:
            counted += abs(value)
    if counted <= 0:
        print("workings: workings.json counts nothing — no period and no register row "
              "is accounted for, so the file is a skeleton rather than an answer")
        return 0.0

    hits = 0
    for path_keys in KEYS:
        expected_value = _dig(want, path_keys)
        actual = _dig(got, path_keys)
        if _match(actual, expected_value):
            hits += 1
        else:
            shown = "(absent)" if actual is MISSING else repr(actual)
            print(f"workings: {'.'.join(path_keys)} expected {expected_value!r}, got {shown}")
    return hits / len(KEYS)
