"""The workings record: the headline figure, the population accounting, the definedness block.

`population.rows_before_join` and `population.rows_after_join` are the two numbers that
separate a revenue figure taken at order grain from one taken at line grain, so they are
graded alongside the exclusion counts rather than folded into a single pass/fail.

A record whose `population` block is still the §8 template — every count zero — is a stub
rather than an answer, and scores nothing here, including on the constants the template
already spells out.
"""

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

import rewardkit as rk
from rewardkit import criterion

EXPECTED = Path("/tests/expected/workings.json")
CENT = Decimal("0.01")

COUNTS = (
    ("population", "included"),
    ("population", "excluded", "internal_account"),
    ("population", "excluded", "out_of_period"),
    ("population", "excluded", "cancelled_or_draft"),
    ("population", "rows_before_join"),
    ("population", "rows_after_join"),
)


def _is_template(doc: dict) -> bool:
    """True when the record reports no orders at all under `population`.

    The §8 code block is a template with zeros in it. Copied back unfilled it claims
    an empty population, which §3 rules out — `included` plus the three excluded counts
    must equal the 38 rows of `data/orders.csv`, and this extract has in-scope orders.
    So an all-zero population is a stub, and a stub earns nothing here, including on
    the constants the template already carries.
    """
    population = doc.get("population")
    population = population if isinstance(population, dict) else {}
    excluded = population.get("excluded")
    excluded = excluded if isinstance(excluded, dict) else {}
    counts = [population.get(k) for k in ("included", "rows_before_join", "rows_after_join")]
    counts += [excluded.get(k) for k in ("internal_account", "out_of_period", "cancelled_or_draft")]
    return all(c in (0, 0.0, None, "0", "") for c in counts)


def _load(path: Path, label: str) -> dict:
    if not path.exists():
        print(f"{label}: workings.json was never written")
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"{label}: workings.json is not valid JSON: {type(exc).__name__}: {exc}")
        return {}
    if not isinstance(doc, dict):
        print(f"{label}: workings.json holds a {type(doc).__name__}, not an object")
        return {}
    return doc


_MISSING = object()


def _dig(doc: dict, path: tuple[str, ...]):
    node = doc
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return _MISSING
        node = node[key]
    return node


@criterion(description="total revenue in the reporting currency", shared=True)
def headline_value(workspace: Path) -> float:
    expected = _load(EXPECTED, "headline_value[key]")
    if not expected:
        return 0.0
    got = _load(workspace / "workings.json", "headline_value")
    if not got:
        return 0.0
    if _is_template(got):
        print("headline_value: workings.json is the unfilled §8 template; no figure was derived")
        return 0.0

    want = Decimal(str(expected["value"])).quantize(CENT)
    value = got.get("value", _MISSING)
    if value is _MISSING:
        print("headline_value: no 'value' key")
        return 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        print(
            f"headline_value: 'value' is {value!r} ({type(value).__name__}); the "
            f"definition asks for a JSON number"
        )
        return 0.0
    try:
        have = Decimal(str(value)).quantize(CENT)
    except (InvalidOperation, ValueError):
        print(f"headline_value: 'value' {value!r} is not a decimal number")
        return 0.0
    if have != want:
        print(f"headline_value: expected {want}, got {have}")
        return 0.0
    return 1.0


rk.headline_value(weight=2.0)


@criterion(
    description="population accounting: inclusions, the three exclusion reasons, and the row counts either side of the join",
    shared=True,
)
def population_counts(workspace: Path) -> float:
    expected = _load(EXPECTED, "population_counts[key]")
    if not expected:
        return 0.0
    got = _load(workspace / "workings.json", "population_counts")

    hits = 0
    for path in COUNTS:
        want = _dig(expected, path)
        have = _dig(got, path)
        label = ".".join(path)
        if have is _MISSING:
            print(f"population_counts: no '{label}' key")
            continue
        if isinstance(have, bool) or not isinstance(have, (int, float, str)):
            print(f"population_counts: {label} is {have!r}, not a count")
            continue
        try:
            have_int = int(Decimal(str(have)))
        except (InvalidOperation, ValueError):
            print(f"population_counts: {label} {have!r} is not a whole number")
            continue
        if have_int == int(want):
            hits += 1
        else:
            print(f"population_counts: {label} expected {want}, got {have_int}")
    return hits / len(COUNTS)


rk.population_counts(weight=3.0)


@criterion(
    description="metric name and the definedness block, with the keys present even where the value is null",
)
def definedness_block(workspace: Path) -> float:
    expected = _load(EXPECTED, "definedness_block[key]")
    if not expected:
        return 0.0
    got = _load(workspace / "workings.json", "definedness_block")
    if got and _is_template(got):
        print(
            "definedness_block: workings.json reports no orders anywhere in 'population'; "
            "that is the §8 template with its zeros still in it, not a workings record"
        )
        return 0.0

    hits = 0
    metric = got.get("metric", _MISSING)
    if isinstance(metric, str) and metric.strip().lower() == str(expected["metric"]).lower():
        hits += 1
    else:
        print(f"definedness_block: metric expected {expected['metric']!r}, got {metric!r}")

    undefined = got.get("undefined", _MISSING)
    if isinstance(undefined, bool) and undefined is expected["undefined"]:
        hits += 1
    else:
        print(
            f"definedness_block: 'undefined' expected the boolean "
            f"{expected['undefined']!r}, got {undefined!r}"
        )

    for key in ("undefined_reason", "denominator"):
        if key not in got:
            print(f"definedness_block: no {key!r} key; the definition requires it even when null")
            continue
        if got[key] is expected[key]:
            hits += 1
        else:
            print(f"definedness_block: {key} expected {expected[key]!r}, got {got[key]!r}")

    return hits / 4
