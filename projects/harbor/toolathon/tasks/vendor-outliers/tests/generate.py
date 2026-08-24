"""Deterministic generator for the vendor-outliers environment and its ground truth.

This lives under tests/grading/ rather than environment/task/ on purpose: the
Dockerfile copies environment/task/ wholesale into /harbor_task, so anything that
reveals the answer has to stay outside it. new_task.py lint enforces exactly this.

    python tests/grading/generate.py           regenerate ledgers, vendor master, ground truth
    python tests/grading/generate.py --check   the above, then prove every planted trap bites

The generator plants the answer, then makes the *reference solver* recompute it from
the workbooks it just wrote and asserts the two agree. Without that assertion a
generator bug would quietly become the correct answer.
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import statistics as st
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from random import Random

from openpyxl import Workbook, load_workbook

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "environment" / "task" / "initial_workspace"
EXPECTED = ROOT / "tests" / "expected"

SEED = 20250819
STAMP = datetime(2025, 7, 1, 9, 0, 0)  # fixed, so reruns do not churn the files

MONTHS = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06"]
ABBR = {"2025-01": "Jan", "2025-02": "Feb", "2025-03": "Mar",
        "2025-04": "Apr", "2025-05": "May", "2025-06": "Jun"}
# Deliberately uneven: "read sheet 1 and 2" must not be a winning strategy.
RUNS = {"2025-01": 3, "2025-02": 2, "2025-03": 4, "2025-04": 3, "2025-05": 2, "2025-06": 4}
RUN_DAYS = {2: [7, 21], 3: [5, 14, 25], 4: [4, 11, 19, 27]}
# Workbooks that open on the recap tab rather than a payment run.
ACTIVE_IS_SUMMARY = {"2025-02", "2025-04", "2025-06"}

SUMMARY_SHEET = "Summary (provisional)"

# name, category, owner, alias, base spend, invoices/month, profile
VENDORS = [
    ("Acme Industrial", "Manufacturing", "R. Iyer", "Acme Industrial Ltd.", 12000, 7, "clean"),
    ("Borealis Freight", "Logistics", "M. Okafor", "", 4200, 4, "spike"),
    ("Cortex Systems", "IT Services", "S. Lindqvist", "Cortex Systems Inc.", 8000, 4, "clean"),
    ("Delta Print", "Marketing", "M. Okafor", "", 1500, 3, "spike"),
    ("Evergreen Facilities", "Facilities", "T. Baptiste", "", 6000, 4, "clean"),
    ("Fulcrum Legal", "Professional Services", "S. Lindqvist", "", 30000, 3, "single"),
    ("Granite Supplies", "Office Supplies", "T. Baptiste", "", 5000, 7, "near"),
    ("Harbor Analytics", "IT Services", "S. Lindqvist", "Harbour Analytics", 2000, 3, "clean"),
    ("Ionic Labs", "R&D", "R. Iyer", "", 15000, 4, "clean"),
    ("Juniper Catering", "Facilities", "T. Baptiste", "", 900, 3, "clean"),
    ("Kestrel Logistics", "Logistics", "M. Okafor", "", 7400, 4, "spike"),
    ("Lumen Energy", "Utilities", "T. Baptiste", "Lumen Energy PLC", 9100, 3, "clean"),
    ("Meridian Consulting", "Professional Services", "S. Lindqvist", "", 11000, 4, "near"),
    ("Northwind Tooling", "Manufacturing", "R. Iyer", "", 6800, 7, "clean"),
    ("Orchid Media", "Marketing", "M. Okafor", "", 3300, 4, "clean"),
    ("Pinnacle Security", "Facilities", "T. Baptiste", "", 4600, 3, "clean"),
    ("Quarry Materials", "Manufacturing", "R. Iyer", "", 13500, 7, "spike"),
    ("Redwood Travel", "Travel", "M. Okafor", "Redwood Travel Group", 5700, 7, "spike"),
    ("Sable Cleaning", "Facilities", "T. Baptiste", "", 2400, 3, "clean"),
    ("Thorne Instruments", "R&D", "R. Iyer", "", 10200, 4, "near"),
    ("Umbra Design", "Marketing", "M. Okafor", "", 2800, 3, "clean"),
    ("Vertex Staffing", "HR Services", "K. Adeyemi", "Vertex Staffing LLC", 8800, 4, "clean"),
    ("Willow Pharma", "R&D", "R. Iyer", "", 16500, 4, "single"),
    ("Xenon Networks", "IT Services", "S. Lindqvist", "", 7200, 4, "spike"),
    ("Yarrow Foods", "Facilities", "T. Baptiste", "", 1900, 3, "clean"),
    ("Zephyr Couriers", "Logistics", "M. Okafor", "", 3100, 4, "near"),
    ("Alder Insurance", "Professional Services", "K. Adeyemi", "", 12800, 3, "clean"),
    ("Basalt Hardware", "Office Supplies", "T. Baptiste", "", 4400, 4, "clean"),
    ("Cedar Audit", "Professional Services", "K. Adeyemi", "", 21000, 3, "single"),
    ("Dune Telecom", "Utilities", "N. Ferreira", "Dune Telecom AG", 6300, 4, "spike"),
]

# The traps. Each one has to move the final register or it is decoration.
ALIAS_SPLIT = "Redwood Travel"      # rows split across spellings, and it spikes
LATE_RUN_SPIKE = ("Kestrel Logistics", "2025-03")  # flag lives in the final run of a 4-run month
DUPLICATE = ("Orchid Media", "2025-04")            # double-counting it manufactures a false flag
SINGLE_MONTH = {"Fulcrum Legal": "2025-05", "Willow Pharma": "2025-02", "Cedar Audit": "2025-06"}
SPIKE_MONTH = {"Borealis Freight": "2025-06", "Delta Print": "2025-05",
               "Kestrel Logistics": "2025-03", "Quarry Materials": "2025-01",
               "Redwood Travel": "2025-06", "Xenon Networks": "2025-04",
               "Dune Telecom": "2025-02"}
NEAR_MONTH = {"Granite Supplies": "2025-06", "Meridian Consulting": "2025-03",
              "Thorne Instruments": "2025-05", "Zephyr Couriers": "2025-01"}

def threshold_value(others: list[float]) -> float:
    """The month total that would sit exactly on mean + 2 population sigma.

    Solved numerically rather than algebraically: adding the value changes both
    the mean and the spread, so it is its own fixed point.
    """
    lo, hi = max(others), max(others) * 50
    for _ in range(200):
        mid = (lo + hi) / 2
        vals = others + [mid]
        if mid > st.fmean(vals) + 2 * st.pstdev(vals):
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2

def plan_totals(rng: Random) -> dict[str, dict[str, int]]:
    """Decide every vendor's monthly totals up front, so the answer is by construction."""
    totals: dict[str, dict[str, int]] = {}
    for name, _cat, _own, _alias, base, _n, profile in VENDORS:
        if profile == "single":
            month = SINGLE_MONTH[name]
            totals[name] = {month: int(base * rng.uniform(0.97, 1.03))}
            continue

        series = {m: int(base * rng.uniform(0.95, 1.05)) for m in MONTHS}
        if profile in ("spike", "near"):
            target = SPIKE_MONTH[name] if profile == "spike" else NEAR_MONTH[name]
            others = [series[m] for m in MONTHS if m != target]
            edge = threshold_value(others)
            # Comfortably over for a spike; just under for a near miss.
            series[target] = int(edge * (1.25 if profile == "spike" else 0.995))
        totals[name] = series
    return totals

def split_amount(total: int, parts: int, rng: Random) -> list[int]:
    """Break a month total into individual invoices that sum to it exactly."""
    if parts == 1:
        return [total]
    cuts = sorted(rng.uniform(0.15, 0.85) for _ in range(parts - 1))
    shares, prev = [], 0.0
    for c in cuts + [1.0]:
        shares.append(max(c - prev, 0.05))
        prev = c
    scale = total / sum(shares)
    amounts = [max(int(s * scale), 25) for s in shares[:-1]]
    amounts.append(total - sum(amounts))
    if amounts[-1] < 25:  # pathological split; fall back to something even
        even = total // parts
        amounts = [even] * (parts - 1) + [total - even * (parts - 1)]
    return amounts

def spelling(vendor: str, month: str, index: int) -> str:
    """How accounts payable happened to key this vendor on this row."""
    alias = dict((v[0], v[3]) for v in VENDORS)[vendor]
    if vendor == ALIAS_SPLIT:
        if month in ("2025-03", "2025-04"):
            return alias
        if month == "2025-05":
            return "REDWOOD  TRAVEL"          # case and spacing only; not a listed alias
        if month == "2025-06":
            return alias if index % 2 else vendor  # both spellings inside one month
        return vendor
    if alias and month in ("2025-03", "2025-04"):
        return alias
    return vendor

def build_rows(totals, rng: Random):
    """Lay every invoice out into (month -> run index -> rows), plus the duplicates."""
    rows: dict[str, dict[int, list]] = {m: defaultdict(list) for m in MONTHS}
    counter = {m: 0 for m in MONTHS}
    planted_duplicates = []

    for month in MONTHS:
        n_runs = RUNS[month]
        days = RUN_DAYS[n_runs]
        # A sparse end-of-month catch-up run: only a few vendors land in it, so the
        # recap tab stays right for nearly everyone and wrong where it matters.
        catch_up = {LATE_RUN_SPIKE[0]} if LATE_RUN_SPIKE[1] == month else set()
        if DUPLICATE[1] == month:
            catch_up.add(DUPLICATE[0])
        pool = [v[0] for v in VENDORS if month in totals[v[0]] and v[0] not in catch_up]
        catch_up |= set(rng.sample(sorted(pool), 2))

        for name, _cat, _own, _alias, _base, per_month, _profile in VENDORS:
            series = totals[name]
            if month not in series:
                continue
            amounts = split_amount(series[month], per_month, rng)
            amounts.sort(reverse=True)
            for i, amount in enumerate(amounts):
                counter[month] += 1
                invoice = f"INV-{month.replace('-', '')}-{counter[month]:04d}"
                # The catch-up run carries the biggest invoice of the vendors in it.
                if name in catch_up and i == 0:
                    run = n_runs - 1
                else:
                    run = rng.randrange(0, max(n_runs - 1, 1))
                date = f"{month}-{days[run]:02d}"
                rows[month][run].append([date, spelling(name, month, i), invoice, amount])

    # The duplicate: the same invoice re-keyed into the catch-up run. It never changes
    # the intended total (that is deduplicated), only what a naive solver computes.
    dup_vendor, dup_month = DUPLICATE
    n_runs = RUNS[dup_month]
    others = [totals[dup_vendor][m] for m in MONTHS if m != dup_month]
    needed = threshold_value(others) - totals[dup_vendor][dup_month]
    target = int(max(needed, 0) + totals[dup_vendor][dup_month] * 0.25)
    original = None
    for run in range(n_runs):
        for row in rows[dup_month][run]:
            if row[1] == dup_vendor and (original is None or row[3] > original[3]):
                original = row
    if original is None:
        raise SystemExit(f"no {dup_vendor} row in {dup_month} to duplicate")
    # Re-shape that vendor's month so its largest invoice is the amount we need.
    vendor_rows = [r for run in range(n_runs) for r in rows[dup_month][run] if r[1] == dup_vendor]
    month_total = sum(r[3] for r in vendor_rows)
    if target >= month_total:
        raise SystemExit(f"duplicate target {target} exceeds {dup_vendor}'s {dup_month} total {month_total}")
    rest = split_amount(month_total - target, len(vendor_rows) - 1, rng)
    original[3] = target
    for row, amount in zip((r for r in vendor_rows if r is not original), rest):
        row[3] = amount
    rows[dup_month][n_runs - 1].append(list(original))
    planted_duplicates.append((dup_vendor, dup_month, original[2], target))

    # A couple of harmless re-keys elsewhere, so the duplicate is not a lone oddity.
    # These cannot touch the intended answer -- it is computed from unique invoices.
    for month in ("2025-01", "2025-06"):
        run = RUNS[month] - 1
        source = rows[month][0][0]
        rows[month][run].append(list(source))
        planted_duplicates.append((source[1], month, source[2], source[3]))

    return rows, planted_duplicates

def write_ledgers(rows) -> int:
    (WORKSPACE / "ledger").mkdir(parents=True, exist_ok=True)
    written = 0
    for month in MONTHS:
        n_runs = RUNS[month]
        days = RUN_DAYS[n_runs]
        wb = Workbook()
        wb.remove(wb.active)
        for run in range(n_runs):
            ws = wb.create_sheet(f"Run {run + 1} – {days[run]:02d} {ABBR[month]}")
            ws.append(["Date", "Vendor", "Invoice", "Amount"])
            for row in sorted(rows[month][run], key=lambda r: r[2]):
                ws.append(row)
                written += 1

        # The recap is cut before the final run, which is exactly why it goes stale.
        subtotal: dict[str, int] = defaultdict(int)
        for run in range(n_runs - 1):
            for row in rows[month][run]:
                subtotal[row[1]] += row[3]
        recap = wb.create_sheet(SUMMARY_SHEET)
        recap.append(["Vendor", "Month total"])
        for vendor in sorted(subtotal):
            recap.append([vendor, subtotal[vendor]])

        wb.active = wb.sheetnames.index(SUMMARY_SHEET) if month in ACTIVE_IS_SUMMARY else 0
        wb.properties.created = wb.properties.modified = STAMP
        wb.save(WORKSPACE / "ledger" / f"{month}.xlsx")
    return written

def write_vendor_master() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Vendors"
    ws.append(["Vendor", "Category", "Owner", "Also Known As"])
    for name, category, owner, alias, _base, _n, _profile in VENDORS:
        ws.append([name, category, owner, alias])
    wb.properties.created = wb.properties.modified = STAMP
    wb.save(WORKSPACE / "vendor_master.xlsx")

def load_solver():
    """Load the reference solver out of solution/solve.sh.

    The suite keeps each oracle inline in its solve.sh, so that heredoc is the
    only copy of this computation. Extracting it here rather than keeping a
    second copy is what stops the generator and the oracle drifting apart.
    """
    script = (ROOT / "solution" / "solve.sh").read_text()
    body = script.split("<<'PY'\n", 1)[1].rsplit("\nPY\n", 1)[0]
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader("solve", loader=None))
    exec(compile(body, "solve.sh:PY", "exec"), module.__dict__)
    return module


def matches_expected(produced: Path) -> tuple[bool, str]:
    """Compare a produced register against tests/expected/ the way the grader does.

    Deliberately a local reimplementation rather than an import of tests/register.py:
    that module needs rewardkit, and this is a developer tool that should run with
    nothing but openpyxl.
    """
    def read(path):
        sheet = load_workbook(path, data_only=True).active
        rows = list(sheet.iter_rows(values_only=True))
        entries, total = {}, None
        for r in rows[1:]:
            if r is None or all(c is None for c in r):
                continue
            if str(r[0]).strip().lower() == "total flagged:":
                total = str(r[1]).strip()
                continue
            if r[0] is None:
                continue
            entries[(str(r[0]).strip().lower(), str(r[1]).strip())] = tuple(
                str(c).strip().upper() for c in r[2:6])
        return entries, total

    got, got_total = read(produced)
    want, want_total = read(EXPECTED / "exception_register.xlsx")
    if got_total != want_total:
        return False, f"'Total flagged:' reads {got_total!r}, expected {want_total!r}"
    if set(got) != set(want):
        missing = sorted(set(want) - set(got))
        return False, f"row set differs; missing {missing[:3]}"
    wrong = [k for k in want if got[k] != want[k]]
    if wrong:
        return False, f"{len(wrong)} row(s) incorrect, e.g. {wrong[0]}"
    return True, "matches"


def naive_totals(ws: Path, *, alias: bool, dedupe: bool, all_sheets: bool, solve):
    """The reference computation with exactly one safeguard removed."""
    names = solve.registered_names(ws) if alias else {}
    totals: dict[str, dict[str, float]] = defaultdict(dict)
    for book in sorted((ws / "ledger").glob("*.xlsx")):
        month = book.stem
        seen: set[str] = set()
        wb = load_workbook(book, data_only=True)
        sheets = wb.worksheets if all_sheets else [wb.active]
        for sheet in sheets:
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                continue
            header = solve._header(rows[0])
            if not solve.INVOICE_COLUMNS <= set(header):
                continue
            vi, ii, ai = header.index("vendor"), header.index("invoice"), header.index("amount")
            for r in rows[1:]:
                if r is None or r[vi] is None:
                    continue
                invoice = str(r[ii]).strip()
                if dedupe:
                    if invoice in seen:
                        continue
                    seen.add(invoice)
                vendor = names.get(solve._key(r[vi]), str(r[vi]).strip()) if alias else str(r[vi]).strip()
                totals[vendor][month] = totals[vendor].get(month, 0) + float(r[ai])
    return totals

def summary_totals(ws: Path, solve):
    """What an agent gets by trusting the recap tabs instead of the invoices."""
    names = solve.registered_names(ws)
    totals: dict[str, dict[str, float]] = defaultdict(dict)
    for book in sorted((ws / "ledger").glob("*.xlsx")):
        month = book.stem
        for sheet in load_workbook(book, data_only=True).worksheets:
            if sheet.title != SUMMARY_SHEET:
                continue
            for r in list(sheet.iter_rows(values_only=True))[1:]:
                if r is None or r[0] is None:
                    continue
                vendor = names.get(solve._key(r[0]), str(r[0]).strip())
                totals[vendor][month] = totals[vendor].get(month, 0) + float(r[1])
    return totals

def check(planted, duplicates, solve) -> int:
    failures = []

    computed = solve.monthly_totals(WORKSPACE)
    if computed != {v: {m: float(t) for m, t in s.items()} for v, s in planted.items()}:
        only_planted = {v: s for v, s in planted.items() if v not in computed}
        only_computed = {v: s for v, s in computed.items() if v not in planted}
        failures.append(f"solver disagrees with the planted totals; "
                        f"planted-only={list(only_planted)[:4]} computed-only={list(only_computed)[:4]}")

    flagged, thin = solve.build(computed)
    print(f"  ground truth: {len(flagged)} flagged, {len(thin)} insufficient-history")
    for vendor, month, *_ in flagged:
        print(f"    FLAGGED  {vendor}  {month}")
    for vendor, month, _amount in thin:
        print(f"    THIN     {vendor}  {month}")

    # Every trap must actually move the register.
    naive = {
        "reads only the active sheet":
            lambda: naive_totals(WORKSPACE, alias=True, dedupe=True, all_sheets=False, solve=solve),
        "does not resolve vendor aliases":
            lambda: naive_totals(WORKSPACE, alias=False, dedupe=True, all_sheets=True, solve=solve),
        "does not de-duplicate invoices":
            lambda: naive_totals(WORKSPACE, alias=True, dedupe=False, all_sheets=True, solve=solve),
        "trusts the provisional recap tabs":
            lambda: summary_totals(WORKSPACE, solve),
    }
    with tempfile.TemporaryDirectory() as tmp:
        for label, fn in naive.items():
            out = Path(tmp) / label.replace(" ", "_")
            out.mkdir()
            f, t = solve.build(fn())
            solve.write(out, f, t)
            passed, message = matches_expected(out / "exception_register.xlsx")
            if passed:
                failures.append(f"a solver that {label} still passes -- that trap is decoration")
            else:
                print(f"  trap holds: a solver that {label} fails ({message[:60]})")

    print(f"  planted {len(duplicates)} duplicate invoice row(s): "
          + ", ".join(f"{v} {m} {inv}" for v, m, inv, _ in duplicates))

    for f in failures:
        print(f"  FAIL: {f}")
    return 1 if failures else 0

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="after generating, verify the answer and that every trap bites")
    args = parser.parse_args()

    rng = Random(SEED)
    planted = plan_totals(rng)
    rows, duplicates = build_rows(planted, rng)

    if (WORKSPACE / "ledger").exists():
        shutil.rmtree(WORKSPACE / "ledger")
    written = write_ledgers(rows)
    write_vendor_master()
    print(f"wrote {written} invoice rows across {len(MONTHS)} workbooks, {len(VENDORS)} vendors")

    solve = load_solver()
    flagged, thin = solve.build(solve.monthly_totals(WORKSPACE))
    EXPECTED.mkdir(parents=True, exist_ok=True)
    solve.write(EXPECTED, flagged, thin)
    print(f"wrote ground truth to {EXPECTED.relative_to(ROOT)}")

    return check(planted, duplicates, solve) if args.check else 0

if __name__ == "__main__":
    sys.exit(main())
