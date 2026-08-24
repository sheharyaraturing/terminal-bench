#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# build_fixture.sh — journal-balance-forensics
#
# Emits, into the directory this script lives in:
#   journal.jsonl   400 double-entry general-ledger lines, one JSON object per
#                   line, grouped into 140 entries (entry_id JE-0001..JE-0140).
#   extra.sql       CREATE TABLE gl_period_close + INSERT rows. Creates a NEW
#                   table only; it never touches the eight tables baked into the
#                   base image.
#   GROUND_TRUTH.md written by the read-back stage at the bottom of this file,
#                   which re-opens the two emitted artefacts from disk with
#                   separate code and reports what they actually contain.
#
# DETERMINISM: the only source of randomness is random.Random(20240815). Every
# amount, date, account and currency is drawn from that seeded stream in a fixed
# order, so a re-run produces byte-identical files. Verify with:
#     sha256sum journal.jsonl extra.sql
#
# Run:  bash build_fixture.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

python3 - <<'BUILD'
import json, random
from datetime import date, timedelta

rng = random.Random(20240815)

# ── Chart of accounts ────────────────────────────────────────────────────────
COA = {
    "1010": "Cash - Operating",
    "1200": "Accounts Receivable",
    "1400": "Inventory",
    "1600": "Prepaid Expenses",
    "2010": "Accounts Payable",
    "2100": "Accrued Liabilities",
    "2300": "Deferred Revenue",
    "4010": "Product Revenue",
    "4020": "Services Revenue",
    "5010": "Cost of Goods Sold",
    "5210": "Professional Fees",
    "5300": "Payroll Expense",
    "5400": "Facilities Expense",
    "6100": "Depreciation Expense",
}

PERIODS = ["2024-04", "2024-05", "2024-06", "2024-07", "2024-08", "2024-09"]
SOURCES = ["AP_SUBLEDGER", "AR_SUBLEDGER", "PAYROLL_FEED", "MANUAL", "REV_REC"]

# Ordinary two-sided templates: (debit account, credit account, memo)
TEMPLATES = [
    ("5010", "1400", "Cost of goods relieved on shipment"),
    ("5300", "2100", "Payroll accrual"),
    ("5400", "2010", "Facilities charge"),
    ("6100", "1600", "Monthly depreciation run"),
    ("1200", "4010", "Product invoice raised"),
    ("1200", "4020", "Services invoice raised"),
    ("1010", "1200", "Customer receipt applied"),
    ("2010", "1010", "Vendor payment run"),
    ("2300", "4020", "Deferred revenue released"),
    ("1400", "2010", "Inventory receipt"),
]

lines = []          # list of dicts, written in order
counter = 0

def money(v):
    return round(float(v) + 0.0, 2)

def emit(entry_id, period, currency, posted_at, source, rows):
    """rows: list of (account, debit, credit, memo)"""
    for i, (acct, dr, cr, memo) in enumerate(rows, start=1):
        lines.append({
            "entry_id": entry_id,
            "line_no": i,
            "account": acct,
            "account_name": COA[acct],
            "debit": money(dr),
            "credit": money(cr),
            "currency": currency,
            "period": period,
            "posted_at": posted_at,
            "memo": memo,
            "source": source,
        })

def in_period_day(period, day):
    y, m = period.split("-")
    return f"{y}-{m}-{day:02d}"

# ── Scripted special entries, keyed by entry number ─────────────────────────
# L1  five entries whose debits do not equal their credits
UNBALANCED = {
    18:  ("2024-04", "USD", 4, "MANUAL",
          [("5400", 12400.00, 0.00, "Q1 true-up of shared-services allocation"),
           ("2010", 0.00, 12040.00, "Q1 true-up of shared-services allocation")]),
    47:  ("2024-05", "USD", 21, "AP_SUBLEDGER",
          [("5010", 8750.00, 0.00, "Freight-in reclass"),
           ("1400", 0.00, 8750.50, "Freight-in reclass")]),
    73:  ("2024-06", "USD", 12, "MANUAL",
          [("1400", 45000.00, 0.00, "Bonded-warehouse stock transfer"),
           ("2010", 0.00, 4500.00, "Bonded-warehouse stock transfer")]),
    98:  ("2024-07", "GBP", 9, "MANUAL",
          [("5300", 3215.75, 0.00, "Contractor timesheet correction"),
           ("2100", 0.00, 3251.75, "Contractor timesheet correction")]),
    121: ("2024-08", "USD", 15, "REV_REC",
          [("2300", 19880.00, 0.00, "Annual licence revenue release"),
           ("4020", 0.00, 21000.00, "Annual licence revenue release")]),
}

# Decoy: balanced at zero. Looks broken to any "flag the zero amounts" filter.
ZERO_ENTRY = 55

# L2a: balanced entry booked into a period the close table marks CLOSED, with a
# posting timestamp AFTER that period's close date.
LATE_AFTER_CLOSE = 64          # period 2024-05, posted 2024-06-19, close 2024-06-07

# Near-miss: posted on the close date itself. Legitimate - the books were still
# open on that date.
LATE_ON_CLOSE = 82             # period 2024-06, posted 2024-07-05, close 2024-07-05

# Further legitimate out-of-month postings, all comfortably before their close
# date, so that "posted_at month != period" alone yields six candidates and only
# the period-close reference separates them.
LATE_BUT_CLEAN = {
    29:  ("2024-04", "2024-05-02"),
    58:  ("2024-05", "2024-06-03"),
    91:  ("2024-07", "2024-08-01"),
    112: ("2024-07", "2024-08-05"),
}

# L2b: reversal pairs. Four offset cleanly. One reverses the amount but is
# booked in a different currency from the original, so it does not offset.
#   original -> (entry no, period, currency, day, dr acct, cr acct, amount, memo)
REVERSALS = [
    # (orig_no, orig_period, orig_ccy, orig_day, rev_no, rev_period, rev_ccy,
    #  rev_day, dr, cr, amount, subject)
    (24, "2024-04", "USD", 22, 35, "2024-05", "USD", 6, "5400", "2010",
     7325.00, "Duplicate January facilities invoice"),
    (41, "2024-05", "GBP", 14, 52, "2024-05", "GBP", 27, "5010", "1400",
     2140.60, "Mis-shipped inventory relief"),
    (79, "2024-06", "EUR", 18, 106, "2024-07", "USD", 11, "5210", "2010",
     18450.00, "Q2 statutory audit fee - Hansen & Roth GmbH"),   # <-- the defect
    (88, "2024-06", "USD", 25, 95, "2024-07", "USD", 4, "1200", "4010",
     5610.00, "Invoice raised against cancelled order"),
    (109, "2024-07", "EUR", 19, 117, "2024-08", "EUR", 8, "5300", "2100",
     9880.00, "Severance accrual booked twice"),
]
REV_ORIG = {r[0]: r for r in REVERSALS}
REV_BACK = {r[4]: r for r in REVERSALS}

# L2b, second defect: a reversal that names its original and matches it on currency
# AND amount, but posts its credit to the WRONG account, so it does not actually
# reverse the account the original charged. A currency check and an amount check
# both pass; only comparing the accounts catches it.
#   original JE-0131: debit 6100 Depreciation / credit 2100 Accrued Liabilities
#   reversal JE-0138: debit 2100 / credit 5400 Facilities  (should credit 6100)
WRONG_REV = {
    "orig_no": 131, "orig_period": "2024-08", "orig_day": 20,
    "rev_no": 138,  "rev_period": "2024-09",  "rev_day": 9,
    "ccy": "USD", "amount": 15300.00,
    "orig_dr": "6100", "orig_cr": "2100",   # original debits 6100, credits 2100
    "rev_wrong_cr": "5400",                 # reversal debits 2100, credits 5400 (not 6100)
    "subj": "Q3 catch-up depreciation on plant and equipment",
}

# ── Generate 140 entries ────────────────────────────────────────────────────
# Line budget: the scripted entries are all two-line. The filler entries are
# sized so the file lands on exactly 400 lines.
N_ENTRIES = 140
scripted = set(UNBALANCED) | {ZERO_ENTRY, LATE_AFTER_CLOSE, LATE_ON_CLOSE} \
           | set(REV_ORIG) | set(REV_BACK) \
           | {WRONG_REV["orig_no"], WRONG_REV["rev_no"]}
n_filler = N_ENTRIES - len(scripted)
# every entry contributes >= 2 lines; distribute the surplus over filler entries
surplus = 400 - 2 * N_ENTRIES          # extra lines to hand out
extra_line_entries = set()
_pool = [n for n in range(1, N_ENTRIES + 1) if n not in scripted]
rng.shuffle(_pool)
for n in _pool[:surplus]:
    extra_line_entries.add(n)

def period_for(n):
    # entries march forward through the six periods
    idx = min(len(PERIODS) - 1, (n - 1) * len(PERIODS) // N_ENTRIES)
    return PERIODS[idx]

for n in range(1, N_ENTRIES + 1):
    eid = f"JE-{n:04d}"

    if n in UNBALANCED:
        period, ccy, day, src, rows = UNBALANCED[n]
        emit(eid, period, ccy, in_period_day(period, day), src, rows)
        continue

    if n == ZERO_ENTRY:
        period = "2024-05"
        emit(eid, period, "USD", in_period_day(period, 30), "MANUAL", [
            ("1600", 0.00, 0.00,
             "Placeholder - annual broker insurance accrual, amount pending confirmation"),
            ("2100", 0.00, 0.00,
             "Placeholder - annual broker insurance accrual, amount pending confirmation"),
        ])
        continue

    if n == LATE_AFTER_CLOSE:
        emit(eid, "2024-05", "USD", "2024-06-19", "MANUAL", [
            ("5400", 26750.00, 0.00, "May sublease charge omitted from the accrual run"),
            ("2010", 0.00, 26750.00, "May sublease charge omitted from the accrual run"),
        ])
        continue

    if n == LATE_ON_CLOSE:
        emit(eid, "2024-06", "USD", "2024-07-05", "MANUAL", [
            ("5300", 14200.00, 0.00, "June commission accrual, final close adjustment"),
            ("2100", 0.00, 14200.00, "June commission accrual, final close adjustment"),
        ])
        continue

    if n in REV_ORIG:
        (_o, op, occ, oday, _r, _rp, _rc, _rday, dr, cr, amt, subj) = REV_ORIG[n]
        emit(eid, op, occ, in_period_day(op, oday), "AP_SUBLEDGER", [
            (dr, amt, 0.00, subj),
            (cr, 0.00, amt, subj),
        ])
        continue

    if n in REV_BACK:
        (o, _op, _occ, _oday, _r, rp, rcc, rday, dr, cr, amt, subj) = REV_BACK[n]
        emit(eid, rp, rcc, in_period_day(rp, rday), "MANUAL", [
            (cr, amt, 0.00, f"Reversal of JE-{o:04d} - {subj}"),
            (dr, 0.00, amt, f"Reversal of JE-{o:04d} - {subj}"),
        ])
        continue

    if n == WRONG_REV["orig_no"]:
        W = WRONG_REV
        emit(eid, W["orig_period"], W["ccy"], in_period_day(W["orig_period"], W["orig_day"]),
             "MANUAL", [
                 (W["orig_dr"], W["amount"], 0.00, W["subj"]),
                 (W["orig_cr"], 0.00, W["amount"], W["subj"]),
             ])
        continue

    if n == WRONG_REV["rev_no"]:
        W = WRONG_REV
        # a correct reversal would debit orig_cr and credit orig_dr; this one credits
        # rev_wrong_cr instead, so it does not reverse the account the original charged.
        emit(eid, W["rev_period"], W["ccy"], in_period_day(W["rev_period"], W["rev_day"]),
             "MANUAL", [
                 (W["orig_cr"], W["amount"], 0.00, f"Reversal of JE-{W['orig_no']:04d} - {W['subj']}"),
                 (W["rev_wrong_cr"], 0.00, W["amount"], f"Reversal of JE-{W['orig_no']:04d} - {W['subj']}"),
             ])
        continue

    # ── filler: an ordinary balanced entry ──
    period = period_for(n)
    dr_acct, cr_acct, memo = TEMPLATES[rng.randrange(len(TEMPLATES))]
    ccy = "USD" if rng.random() < 0.80 else ("EUR" if rng.random() < 0.55 else "GBP")
    # Professional Fees is reserved: only the audit-fee pair touches 5210, so the
    # uncleared EUR position on that account is unambiguous.
    if dr_acct == "5210":
        dr_acct = "5400"
    total = round(rng.uniform(400, 62000), 2)
    if n in LATE_BUT_CLEAN:
        period, posted = LATE_BUT_CLEAN[n][0], LATE_BUT_CLEAN[n][1]
    else:
        posted = in_period_day(period, rng.randint(1, 28))
    src = SOURCES[rng.randrange(len(SOURCES))]

    if n in extra_line_entries:
        # split the debit side across two lines so the entry has three lines
        first = round(total * round(rng.uniform(0.25, 0.7), 4), 2)
        second = round(total - first, 2)
        rows = [(dr_acct, first, 0.00, memo),
                (dr_acct, second, 0.00, memo + " (second tranche)"),
                (cr_acct, 0.00, round(first + second, 2), memo)]
    else:
        rows = [(dr_acct, total, 0.00, memo),
                (cr_acct, 0.00, total, memo)]
    emit(eid, period, ccy, posted, src, rows)

assert len(lines) == 400, len(lines)

with open("journal.jsonl", "w", encoding="utf-8") as fh:
    for rec in lines:
        fh.write(json.dumps(rec, sort_keys=False, ensure_ascii=True) + "\n")

# ── extra.sql : the period-close reference table ────────────────────────────
CLOSE_ROWS = [
    ("2024-01", "2024-02-06", "CLOSED",     "m.okafor"),
    ("2024-02", "2024-03-07", "CLOSED",     "m.okafor"),
    ("2024-03", "2024-04-05", "CLOSED",     "m.okafor"),
    ("2024-04", "2024-05-08", "CLOSED",     "m.okafor"),
    ("2024-05", "2024-06-07", "CLOSED",     "d.vasquez"),
    ("2024-06", "2024-07-05", "CLOSED",     "d.vasquez"),
    ("2024-07", "2024-08-06", "CLOSED",     "d.vasquez"),
    ("2024-08", "",           "ADJUSTING",  "d.vasquez"),
    ("2024-09", "",           "OPEN",       ""),
]
with open("extra.sql", "w", encoding="utf-8") as fh:
    fh.write(
        "-- journal-balance-forensics fixture.\n"
        "-- Creates ONE NEW table. It does not read, alter or drop any of the eight\n"
        "-- tables baked into the base image, which are shared with other tasks.\n"
        "-- Column types follow the baked convention: TEXT unless every value parses\n"
        "-- as INTEGER or REAL.\n"
        "CREATE TABLE IF NOT EXISTS gl_period_close (\n"
        "  period     TEXT,\n"
        "  close_date TEXT,\n"
        "  status     TEXT,\n"
        "  closed_by  TEXT\n"
        ");\n"
    )
    for p, d, s, by in CLOSE_ROWS:
        fh.write("INSERT INTO gl_period_close (period, close_date, status, closed_by) "
                 f"VALUES ('{p}', '{d}', '{s}', '{by}');\n")

print("built journal.jsonl and extra.sql")
BUILD

# ── READ-BACK STAGE ─────────────────────────────────────────────────────────
# Everything below re-opens the two files that were just written and derives the
# ground truth from THEM, with code that shares no state with the builder above.
# GROUND_TRUTH.md is whatever this stage prints.
python3 - <<'READBACK'
import json, os, sqlite3, tempfile
from collections import defaultdict, OrderedDict

recs = [json.loads(l) for l in open("journal.jsonl", encoding="utf-8")]
COA_LOOKUP = {r["account"]: r["account_name"] for r in recs}

# rebuild the period-close table from extra.sql in a scratch database
tmp = os.path.join(tempfile.mkdtemp(), "scratch.db")
con = sqlite3.connect(tmp)
con.executescript(open("extra.sql", encoding="utf-8").read())
close_date = {}
status = {}
for period, cd, st in con.execute("SELECT period, close_date, status FROM gl_period_close"):
    close_date[period] = cd
    status[period] = st

entries = OrderedDict()
for r in recs:
    entries.setdefault(r["entry_id"], []).append(r)

def s(x):
    return f"{x:,.2f}"

out = []
w = out.append

w("# GROUND_TRUTH.md — journal-balance-forensics")
w("")
w("Everything below was read **back out of the built artefacts** by the read-back")
w("stage of `build_fixture.sh` (`bash build_fixture.sh` regenerates this file). The")
w("journal was re-parsed from `journal.jsonl` line by line; the period-close facts")
w("were obtained by executing `extra.sql` into a scratch SQLite database and")
w("querying it back. No value here comes from the builder's in-memory state.")
w("")
w("## Shape")
w("")
w(f"- `journal.jsonl` lines: **{len(recs)}**")
w(f"- distinct entries: **{len(entries)}** (`{recs[0]['entry_id']}` .. `{recs[-1]['entry_id']}`)")
w(f"- fields per line: `{'`, `'.join(recs[0].keys())}`")
per = defaultdict(int)
for r in recs:
    per[r["period"]] += 1
w("- lines per period: " + ", ".join(f"{k} {v}" for k, v in sorted(per.items())))
cc = defaultdict(int)
for r in recs:
    cc[r["currency"]] += 1
w("- lines per currency: " + ", ".join(f"{k} {v}" for k, v in sorted(cc.items())))
w(f"- distinct accounts used: **{len({r['account'] for r in recs})}**")
w(f"- `gl_period_close` rows: **{len(close_date)}** "
  f"({', '.join(sorted(close_date))})")
w("")

# ── L1 ──
w("## Layer 1 — entries whose debits do not equal their credits")
w("")
imb = []
for eid, rows in entries.items():
    d = round(sum(r["debit"] for r in rows), 2)
    c = round(sum(r["credit"] for r in rows), 2)
    if abs(d - c) > 1e-9:
        imb.append((eid, d, c, round(d - c, 2)))
w(f"count: **{len(imb)}**")
w("")
w("| entry | period | currency | debits | credits | debits - credits |")
w("|---|---|---|---:|---:|---:|")
for eid, d, c, delta in imb:
    r0 = entries[eid][0]
    w(f"| `{eid}` | {r0['period']} | {r0['currency']} | {s(d)} | {s(c)} | {s(delta)} |")
w("")
signed = round(sum(x[3] for x in imb), 2)
absolute = round(sum(abs(x[3]) for x in imb), 2)
biggest = max(imb, key=lambda x: abs(x[3]))
w(f"- signed total of the five differences: **{s(signed)}**")
w(f"- sum of absolute differences: **{s(absolute)}**")
w(f"- largest single imbalance: `{biggest[0]}` at **{s(abs(biggest[3]))}** "
  f"(debits {s(biggest[1])} vs credits {s(biggest[2])} — a one-decimal-place shift "
  f"on the credit side)")
w("")
tot_d = round(sum(r["debit"] for r in recs), 2)
tot_c = round(sum(r["credit"] for r in recs), 2)
bad = {x[0] for x in imb}
rem_d = round(sum(r["debit"] for r in recs if r["entry_id"] not in bad), 2)
rem_c = round(sum(r["credit"] for r in recs if r["entry_id"] not in bad), 2)
w(f"- whole-file totals: debits {s(tot_d)}, credits {s(tot_c)}, "
  f"difference {s(round(tot_d - tot_c, 2))}")
w(f"- with those five entries excluded: debits **{s(rem_d)}**, credits **{s(rem_c)}**, "
  f"difference **{s(round(rem_d - rem_c, 2))}** — the rest of the ledger foots exactly")
w("")

# ── decoy: the zero entry ──
w("## Decoy — the entry that is balanced at zero")
w("")
zeros = [eid for eid, rows in entries.items()
         if all(r["debit"] == 0.0 and r["credit"] == 0.0 for r in rows)]
w(f"entries in which every line is 0.00 / 0.00: **{len(zeros)}** — {', '.join('`'+z+'`' for z in zeros)}")
for z in zeros:
    r0 = entries[z][0]
    w("")
    w(f"- `{z}`: {len(entries[z])} lines, period {r0['period']}, "
      f"accounts {', '.join(r['account'] for r in entries[z])}")
    w(f"  - memo: \"{r0['memo']}\"")
    w(f"  - debits {s(sum(r['debit'] for r in entries[z]))} = "
      f"credits {s(sum(r['credit'] for r in entries[z]))}, so it **balances** and is "
      f"NOT one of the {len(imb)} imbalances above")
w("")

# ── L2a: posted after close ──
w("## Layer 2a — postings dated outside their own period")
w("")
cands = []
for eid, rows in entries.items():
    r0 = rows[0]
    if r0["posted_at"][:7] != r0["period"]:
        cands.append((eid, r0["period"], r0["posted_at"],
                      close_date.get(r0["period"], ""), status.get(r0["period"], "")))
w(f"entries whose `posted_at` month differs from `period`: **{len(cands)}**")
w("")
w("| entry | period | posted_at | period close_date | status | after close? |")
w("|---|---|---|---|---|---|")
violations = []
for eid, p, pa, cd, st in sorted(cands, key=lambda x: x[2]):
    after = bool(cd) and pa > cd
    if after:
        violations.append((eid, p, pa, cd))
    w(f"| `{eid}` | {p} | {pa} | {cd or '(none)'} | {st} | "
      f"{'**YES**' if after else 'no'} |")
w("")
w(f"entries posted strictly after their period's close date: **{len(violations)}**")
for eid, p, pa, cd in violations:
    rows = entries[eid]
    d = round(sum(r["debit"] for r in rows), 2)
    c = round(sum(r["credit"] for r in rows), 2)
    lag = (int(pa[8:10]) - int(cd[8:10])) + 0
    from datetime import date as _d
    lag = (_d(*map(int, pa.split("-"))) - _d(*map(int, cd.split("-")))).days
    w("")
    w(f"- **`{eid}`** — period **{p}** (status `{status[p]}`, closed **{cd}**), "
      f"posted **{pa}**, i.e. **{lag} days after the close**")
    w(f"  - it BALANCES: debits {s(d)} = credits {s(c)}, amount **{s(d)}** "
      f"{rows[0]['currency']}")
    w(f"  - accounts {', '.join(r['account'] + ' ' + r['account_name'] for r in rows)}")
    w(f"  - memo: \"{rows[0]['memo']}\"")
    w(f"  - it is invisible to a debits-vs-credits test; the close date lives only in")
    w(f"    `gl_period_close`, not in the journal file")
near = [c_ for c_ in cands if c_[3] and c_[2] == c_[3]]
w("")
for eid, p, pa, cd, st in near:
    rows = entries[eid]
    w(f"- NEAR-MISS `{eid}` — period {p}, closed {cd}, posted {pa}: posted **on** the")
    w(f"  close date, not after it. The books were still open that day, so it is")
    w(f"  legitimate and must NOT be reported. Amount {s(sum(r['debit'] for r in rows))} "
      f"{rows[0]['currency']}.")
w("")

# ── L2b: reversal pairs ──
w("## Layer 2b — reversal pairs")
w("")
pairs = []
for eid, rows in entries.items():
    m = rows[0]["memo"]
    if m.startswith("Reversal of JE-"):
        orig = m.split()[2].rstrip(" -")
        pairs.append((orig, eid))
w(f"lines whose memo declares a reversal resolve to **{len(pairs)}** original/reversal pairs.")
w("")
w("| original | ccy | reversal | ccy | amount | currencies match? |")
w("|---|---|---|---|---:|---|")
mismatch = []
for orig, rev in sorted(pairs, key=lambda x: x[0]):
    o = entries[orig]
    r = entries[rev]
    oc, rc = o[0]["currency"], r[0]["currency"]
    amt = round(sum(x["debit"] for x in o), 2)
    ok = oc == rc
    if not ok:
        mismatch.append((orig, rev, oc, rc, amt))
    w(f"| `{orig}` | {oc} | `{rev}` | {rc} | {s(amt)} | {'yes' if ok else '**NO**'} |")
w("")
for orig, rev, oc, rc, amt in mismatch:
    o, r = entries[orig], entries[rev]
    w(f"- **`{orig}` / `{rev}` does not offset.** The original is denominated in "
      f"**{oc}**, the reversal in **{rc}**, both for **{s(amt)}**.")
    w(f"  - `{orig}`: {o[0]['period']}, debit {o[0]['account']} "
      f"{o[0]['account_name']} {s(o[0]['debit'])} {oc} / credit {o[1]['account']} "
      f"{o[1]['account_name']} {s(o[1]['credit'])} {oc}")
    w(f"  - `{rev}`: {r[0]['period']}, debit {r[0]['account']} "
      f"{r[0]['account_name']} {s(r[0]['debit'])} {rc} / credit {r[1]['account']} "
      f"{r[1]['account_name']} {s(r[1]['credit'])} {rc}")
    w(f"  - memo on the reversal: \"{r[0]['memo']}\"")
    w(f"  - **both entries balance internally**, so no entry-level "
      f"debits-vs-credits test can see this.")
    w(f"  - net effect: {s(amt)} {oc} of expense is still on the books while "
      f"{s(amt)} {rc} of expense was removed that had never been posted.")
w("")

# reversals that match on currency and amount but post to the WRONG account
w("## Layer 2b (second defect) — reversal booked to the wrong account")
w("")
def _dr_acct(rows):
    return next((x["account"] for x in rows if x["debit"] > 0), None)
def _cr_acct(rows):
    return next((x["account"] for x in rows if x["credit"] > 0), None)
wrong_acct = []
for orig, rev in sorted(pairs, key=lambda x: x[0]):
    o, r = entries[orig], entries[rev]
    if o[0]["currency"] != r[0]["currency"]:
        continue  # that is the currency-mismatch defect, handled above
    o_dr, o_cr = _dr_acct(o), _cr_acct(o)
    r_dr, r_cr = _dr_acct(r), _cr_acct(r)
    # a correct reversal debits the original's credit account and credits its debit account
    if not (r_dr == o_cr and r_cr == o_dr):
        wrong_acct.append((orig, rev, o_dr, o_cr, r_dr, r_cr,
                           round(sum(x["debit"] for x in o), 2), o[0]["currency"]))
w(f"reversals whose currency and amount match the original but whose accounts do not "
  f"mirror it: **{len(wrong_acct)}**")
for orig, rev, o_dr, o_cr, r_dr, r_cr, amt, ccy in wrong_acct:
    w("")
    w(f"- **`{rev}` does not offset `{orig}`.** Same currency ({ccy}) and same amount "
      f"({s(amt)}), and both balance internally, so a currency check, an amount check and "
      f"an entry-level footing check all pass.")
    w(f"  - `{orig}` debited **{o_dr} {COA_LOOKUP.get(o_dr, o_dr)}** and credited {o_cr}.")
    w(f"  - a correct reversal would credit **{o_dr}**; `{rev}` credits **{r_cr} "
      f"{COA_LOOKUP.get(r_cr, r_cr)}** instead, debiting {r_dr}.")
    w(f"  - net effect: the {s(amt)} {ccy} charge on account {o_dr} is never reversed, and "
      f"{s(amt)} {ccy} is wrongly credited to account {r_cr}.")
w("")

# per (account, currency) net, for the account the mismatched pair touches
w("### Per-account, per-currency net for the affected expense account")
w("")
if mismatch:
    acct = entries[mismatch[0][0]][0]["account"]
    acct_name = entries[mismatch[0][0]][0]["account_name"]
    nets = defaultdict(lambda: [0.0, 0.0])
    for r in recs:
        if r["account"] == acct:
            nets[r["currency"]][0] += r["debit"]
            nets[r["currency"]][1] += r["credit"]
    w(f"account **{acct} {acct_name}** is touched by exactly "
      f"**{len({r['entry_id'] for r in recs if r['account'] == acct})}** entries in the "
      f"whole file:")
    w("")
    w("| currency | debits | credits | net |")
    w("|---|---:|---:|---:|")
    for ccy in sorted(nets):
        d, c = nets[ccy]
        w(f"| {ccy} | {s(round(d,2))} | {s(round(c,2))} | {s(round(d - c, 2))} |")
    w("")
    for ccy in sorted(nets):
        d, c = nets[ccy]
        net = round(d - c, 2)
        w(f"- {ccy}: net **{s(net)}**")
w("")
w("## Numbers that appear in no claim")
w("")
w("The filler entries are ordinary balanced postings drawn from a seeded stream.")
w("Their individual amounts are deliberately not asserted anywhere; only the")
w("aggregates above are.")

open("GROUND_TRUTH.md", "w", encoding="utf-8").write("\n".join(out) + "\n")
print("wrote GROUND_TRUTH.md")
READBACK

echo "--- sizes ---"
wc -c journal.jsonl extra.sql GROUND_TRUTH.md
echo "--- checksums ---"
sha256sum journal.jsonl extra.sql
