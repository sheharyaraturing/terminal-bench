"""The supporting figures in workings.json.

One fraction over the leaves of the object the schedule specifies: the two
identifiers, the three population counts, the fee total, the three exclusion
counts, the reason code per undefined account and the five band totals. Grading
the leaves rather than the object means a run that assembles the population
correctly but slips on one figure is distinguishable from one that never derived
the population at all.

Leaves the agent invents under a key the schedule names count against the
denominator, so listing every account as undefined cannot buy a score.
"""

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from rewardkit import criterion

EXPECTED = Path("/tests/expected/workings.json")


def _load(path: Path):
    if not path.exists():
        print(f"workings: {path} is absent")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"workings: {path.name} is not readable JSON: {type(exc).__name__}: {exc}")
        return None
    return data if isinstance(data, dict) else None


def _leaves(data, prefix: str = "") -> dict:
    out = {}
    if isinstance(data, dict):
        for key, value in data.items():
            out.update(_leaves(value, f"{prefix}{key}."))
    else:
        out[prefix.rstrip(".")] = data
    return out


def _same(want, got) -> bool:
    if isinstance(want, str) and isinstance(got, str):
        return want.strip().upper() == got.strip().upper()
    try:
        return Decimal(str(want)) == Decimal(str(got))
    except (InvalidOperation, ValueError):
        return str(want).strip() == str(got).strip()


@criterion(description="the population counts, fee total, reason codes and band totals")
def workings(workspace: Path) -> float:
    want = _load(EXPECTED)
    if want is None:
        return 0.0
    expected = _leaves(want)

    got_doc = _load(workspace / "workings.json")
    if got_doc is None:
        return 0.0
    top = set(want)
    got = {k: v for k, v in _leaves(got_doc).items() if k.split(".")[0] in top}

    hits = 0
    for key, value in expected.items():
        if key in got and _same(value, got[key]):
            hits += 1
        else:
            print(f"workings: {key} expected {value!r}, found {got.get(key, '<absent>')!r}")
    return hits / max(len(expected), len(got))
