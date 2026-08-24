"""The summary figures. A scalar can be right by accident; four cannot.

Nothing here pays for a shell: every criterion needs a figure that could only come
out of the restatement, and the period pin -- three strings the policy publishes
verbatim -- is gated on the restatement existing at all.

Each criterion isolates one failure. A wrong total with the right per-currency counts
is an arithmetic slip; carried_forward_count = 0 means the fixing calendar was never
consulted; undefined_count = 0 means a proxy rate was invented.

Undefined counts are graded as integers, so a missing key, null and "" all fail.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import rewardkit as rk
from rewardkit import criterion

EXPECTED = Path("/tests/expected/workings.json")
CENT = Decimal("0.01")
REASONS = ("NO_RATE_FOR_CURRENCY", "NO_RATE_ON_OR_BEFORE_DATE")


def _load(path: Path, label: str) -> dict:
    if not path.exists():
        print(f"workings: {label} workings.json was not produced")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"workings: {label} workings.json is not valid JSON: {type(exc).__name__}: {exc}")
        return {}
    return payload if isinstance(payload, dict) else {}


def _money(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).strip().replace(",", "")).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


def _count(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


@criterion(description="total USD revenue, to the cent", shared=True)
def total_usd_revenue(workspace: Path) -> float:
    want = _money(_load(EXPECTED, "expected").get("total_usd_revenue"))
    if want is None:
        print("workings: the answer key carries no total; scoring zero")
        return 0.0
    got = _money(_load(workspace / "workings.json", "agent").get("total_usd_revenue"))
    if got != want:
        print(f"workings: total_usd_revenue expected {want}, got {got!r}")
    return 1.0 if got == want else 0.0


rk.total_usd_revenue(weight=2.0)


@criterion(description="transactions counted against the currency they were struck in")
def currency_counts(workspace: Path) -> float:
    want = _load(EXPECTED, "expected").get("transactions_by_currency") or {}
    if not isinstance(want, dict) or not want:
        return 0.0
    raw = _load(workspace / "workings.json", "agent").get("transactions_by_currency")
    got = raw if isinstance(raw, dict) else {}
    normalised = {str(k).strip().upper(): _count(v) for k, v in got.items()}
    hits = sum(1 for code, n in want.items() if normalised.get(str(code).strip().upper()) == n)
    return hits / max(len(want), len(normalised), 1)


@criterion(description="conversions that fell back to an earlier published quote")
def carried_forward_count(workspace: Path) -> float:
    want = _count(_load(EXPECTED, "expected").get("carried_forward_count"))
    if want is None:
        return 0.0
    got = _count(_load(workspace / "workings.json", "agent").get("carried_forward_count"))
    if got != want:
        print(f"workings: carried_forward_count expected {want}, got {got!r}")
    return 1.0 if got == want else 0.0


@criterion(description="undefined conversions, split by the reason the policy names")
def undefined_accounting(workspace: Path) -> float:
    key = _load(EXPECTED, "expected")
    want_total = _count(key.get("undefined_count"))
    want_reasons = key.get("undefined_by_reason") or {}
    if want_total is None or not isinstance(want_reasons, dict):
        return 0.0

    payload = _load(workspace / "workings.json", "agent")
    hits = 1 if _count(payload.get("undefined_count")) == want_total else 0
    raw = payload.get("undefined_by_reason")
    got = raw if isinstance(raw, dict) else {}
    normalised = {str(k).strip().upper(): _count(v) for k, v in got.items()}
    for reason in REASONS:
        if normalised.get(reason) == _count(want_reasons.get(reason)):
            hits += 1
        else:
            print(f"workings: undefined_by_reason[{reason}] expected "
                  f"{want_reasons.get(reason)!r}, got {got.get(reason)!r}")
    return hits / (1 + len(REASONS))


@criterion(description="the metric name and the period it was struck for", shared=True)
def period_pin(workspace: Path) -> float:
    key = _load(EXPECTED, "expected")
    payload = _load(workspace / "workings.json", "agent")

    # These three values are published verbatim in section 7.2, so on their own they
    # are free: an empty shell that copies the skeleton out of the policy would bank
    # them. Pay for them only when they sit on an actual restatement.
    counts = payload.get("transactions_by_currency")
    if not isinstance(counts, dict) or not counts:
        print("workings: transactions_by_currency is empty, so workings.json pins a period "
              "over no restatement; scoring the period pin zero")
        return 0.0

    fields = ("metric", "period_start", "period_end")
    hits = sum(1 for f in fields
               if str(payload.get(f, "")).strip() == str(key.get(f, "")).strip() and key.get(f))
    return hits / len(fields)


rk.period_pin(weight=0.5)
