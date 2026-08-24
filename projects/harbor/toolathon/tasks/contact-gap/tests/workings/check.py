"""The ten figures in workings.json, one tenth of the dimension each.

A scalar can be right by accident; ten consistent figures cannot. The excluded-row
counts are what separate a model that applied the classification from one that
guessed the headline number, so they are graded at the same weight as the headline.
"""

import json
from pathlib import Path

from rewardkit import criterion

EXPECTED = Path("/tests/expected/workings.json")
STRINGS = ("metric", "period_start", "period_end")
COUNTS = ("customers_total", "customers_with_contact", "value",
          "orphan_tickets", "soft_deleted_tickets", "out_of_period_tickets")
RATE = "contact_rate"
TOLERANCE = 1e-9


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        blob = json.loads(path.read_text())
    except Exception as exc:
        print(f"workings: {path.name} is not valid JSON: {type(exc).__name__}: {exc}")
        return {}
    return blob if isinstance(blob, dict) else {}


def _as_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _as_float(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


@criterion(description="the ten figures in workings.json")
def workings(workspace: Path) -> float:
    expected = _load(EXPECTED)
    if not expected:
        print("workings: the answer key could not be read")
        return 0.0
    got = _load(workspace / "workings.json")
    if not got:
        print("workings: workings.json is missing or unreadable")
        return 0.0

    hits = 0
    for key in STRINGS:
        actual = got.get(key)
        if isinstance(actual, str) and actual.strip() == expected[key]:
            hits += 1
        else:
            print(f"workings: {key} is {actual!r}, expected {expected[key]!r}")

    for key in COUNTS:
        actual = _as_int(got.get(key))
        if actual == expected[key]:
            hits += 1
        else:
            print(f"workings: {key} is {got.get(key)!r}, expected {expected[key]}")

    actual = _as_float(got.get(RATE))
    if actual is not None and abs(actual - float(expected[RATE])) <= TOLERANCE:
        hits += 1
    else:
        print(f"workings: {RATE} is {got.get(RATE)!r}, expected {expected[RATE]} "
              "(four decimal places, rounded half-up)")

    return hits / (len(STRINGS) + len(COUNTS) + 1)
