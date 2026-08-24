#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# build_fixture.sh — retention-purge-gap
#
# Emits, into the directory this script lives in:
#   records.csv      400 inventory rows: record_id, class, created_at,
#                    legal_hold. created_at is ISO 8601 WITH the originating
#                    region's UTC offset, which is the crux of the decoy.
#   policy.md        the retention schedule: the snapshot instant, the UTC rule,
#                    the boundary rule, the legal-hold exemption, and six class
#                    entries — one of which carries no window of its own.
#   retention.sql    additive runtime tables for records, hold events, the purge
#                    run, candidates and final deletion receipts.
#   logs/            six bounded purge-worker logs.
#   bundles/retention-platform.bundle
#                    the deterministic internal Git history built from the
#                    pinned sanitized upstream source snapshot and checked-in
#                    overlays, including the post-run regulator return.
#   GROUND_TRUTH.md  the final independent SQL/Git/log read-back.
#
# WHAT IS PLANTED
#   L1     records past their class window at the pinned snapshot instant. One
#          join of five numeric windows onto the inventory finds them.
#   L2a    `session_replay` (§3.6) states NO number. Its window is defined by
#          reference to support correspondence (§3.2). Any per-class lookup that
#          expects a figure in the entry skips the class silently, and with it a
#          fifth of the whole backlog.
#   L2b    legal_hold records are exempt (§2.4) however overdue they are, so the
#          defensible figure is smaller than the overdue figure. The trap inside
#          the trap: most held records are not overdue at all, so subtracting
#          every hold instead of only the overdue holds over-corrects.
#   decoy  records whose LOCAL wall-clock reads on the overdue side of the
#          cut-off while their UTC instant does not. §2.2 says the arithmetic is
#          done in UTC. Dropping the offsets reports them as purgeable — the
#          exact over-statement the persona was pulled up for. A handful of
#          records run the other way, and a naive reading misses those.
#   edge   two records whose age equals their window to the second. §2.3 says
#          eligibility needs the age to EXCEED the window, so they are not yet
#          eligible. The regulator return requires both IDs in the resubmission.
#   lock   the internal worker adapter treats Qumulo/filelock's time-bounded
#          `recent_locks` debounce cache as durable lock truth. Seven cache
#          entries older than the upstream five-second cooldown are skipped.
#
# DETERMINISM: the only source of randomness is random.Random(20260401),
# consumed in a fixed order. Every special record is derived arithmetically from
# its class cut-off, never drawn. Git metadata and operational evidence use fixed
# values. A re-run produces byte-identical evidence.
#
# Run:  bash build_fixture.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

python3 - <<'BUILD'
import csv, random
from datetime import datetime, timedelta, timezone

rng = random.Random(20260401)

SNAPSHOT = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)   # §2.1
LATEST   = datetime(2026, 3, 25, 0, 0, 0, tzinfo=timezone.utc)  # newest record

# class code -> (window in days, earliest plain-overdue date, earliest recent date)
# `session_replay` inherits 540 from `support_corr`; the number lives here in the
# builder but NOT in the policy entry, which is the point.
WINDOW = {
    "txn_log":           90,
    "support_corr":      540,
    "marketing_contact": 1095,
    "audit_trail":       2555,
    "hr_applicant":      730,
    "session_replay":    540,
}
CUTOFF = {c: SNAPSHOT - timedelta(days=d) for c, d in WINDOW.items()}

# Oldest date to draw from, per class, for records on each side of the cut-off.
OLDEST_OVERDUE = {
    "txn_log":           datetime(2025, 6, 1, tzinfo=timezone.utc),
    "support_corr":      datetime(2023, 1, 10, tzinfo=timezone.utc),
    "marketing_contact": datetime(2021, 2, 1, tzinfo=timezone.utc),
    "audit_trail":       None,      # nothing in this class is overdue
    "hr_applicant":      datetime(2022, 5, 1, tzinfo=timezone.utc),
    "session_replay":    datetime(2023, 3, 1, tzinfo=timezone.utc),
}

# Per class: how many of each kind of record to lay down.
#   plain    overdue, no hold, comfortably clear of the cut-off
#   held     overdue, legal_hold = true  -> exempt under §2.4
#   reverse  overdue in UTC, but the local wall-clock reads inside the window
#   decoy    NOT overdue in UTC, but the local wall-clock reads overdue
#   edge     age exactly equal to the window -> not yet eligible (§2.3)
#   recent   inside the window, no hold
#   rhold    inside the window, legal_hold = true  -> a hold that exempts nothing
PLAN = {
    "txn_log":           dict(plain=51, held=5, reverse=2, decoy=3, edge=1, recent=40, rhold=4),
    "support_corr":      dict(plain=27, held=3, reverse=1, decoy=2, edge=0, recent=30, rhold=3),
    "marketing_contact": dict(plain=19, held=4, reverse=1, decoy=1, edge=0, recent=28, rhold=2),
    "hr_applicant":      dict(plain=17, held=2, reverse=0, decoy=1, edge=1, recent=22, rhold=2),
    "session_replay":    dict(plain=30, held=6, reverse=1, decoy=2, edge=0, recent=26, rhold=3),
    # 57 drawn + 2 held + the pinned oldest record below = 60
    "audit_trail":       dict(plain=0,  held=0, reverse=0, decoy=0, edge=0, recent=57, rhold=2),
}

# Regional offsets seen in the inventory, with their weights. The negative ones
# are what make the decoy possible; the positive ones what make the reverse case
# possible.
OFFSETS = ["+00:00", "-05:00", "-08:00", "+02:00", "+05:30", "+09:00", "+10:00"]
OFF_W   = [55, 10, 8, 10, 8, 6, 3]

def off_delta(off):
    sign = 1 if off[0] == "+" else -1
    h, m = int(off[1:3]), int(off[4:6])
    return sign * timedelta(hours=h, minutes=m)

def fmt(utc_instant, off):
    """Render a UTC instant as a local wall-clock stamp carrying its offset."""
    local = utc_instant + off_delta(off)
    return local.strftime("%Y-%m-%dT%H:%M:%S") + off

def draw(lo, hi):
    """Uniform instant in [lo, hi), to the second."""
    span = int((hi - lo).total_seconds())
    return lo + timedelta(seconds=rng.randrange(span))

MARGIN = timedelta(days=5)     # keeps ordinary records far enough from a
                               # cut-off that no offset could move them across

# Fixed offset/gap pairs for the manufactured edge cases. gap < |offset| in every
# case, which is what makes the wall-clock reading land on the wrong side.
DECOY_SPEC = [("-08:00", timedelta(hours=3, minutes=12)),
              ("-08:00", timedelta(hours=6, minutes=41)),
              ("-05:00", timedelta(hours=2, minutes=5)),
              ("-05:00", timedelta(hours=4, minutes=38)),
              ("-08:00", timedelta(hours=7, minutes=3)),
              ("-05:00", timedelta(hours=1, minutes=49)),
              ("-08:00", timedelta(hours=5, minutes=26)),
              ("-05:00", timedelta(hours=3, minutes=57)),
              ("-08:00", timedelta(hours=2, minutes=34))]
REVERSE_SPEC = [("+09:00", timedelta(hours=2, minutes=20)),
                ("+05:30", timedelta(hours=1, minutes=15)),
                ("+10:00", timedelta(hours=4, minutes=44)),
                ("+09:00", timedelta(hours=6, minutes=8)),
                ("+05:30", timedelta(hours=3, minutes=2))]

rows = []
di = ri = 0
for cls in ["txn_log", "support_corr", "marketing_contact", "hr_applicant",
            "session_replay", "audit_trail"]:
    plan, cut = PLAN[cls], CUTOFF[cls]
    old = OLDEST_OVERDUE[cls]

    for kind, n in (("plain", plan["plain"]), ("held", plan["held"])):
        for _ in range(n):
            inst = draw(old, cut - MARGIN)
            rows.append((cls, inst, rng.choices(OFFSETS, OFF_W)[0],
                         "true" if kind == "held" else "false"))

    # overdue in UTC, but the local wall-clock falls AFTER the cut-off
    for _ in range(plan["reverse"]):
        off, gap = REVERSE_SPEC[ri]; ri += 1
        rows.append((cls, cut - gap, off, "false"))

    # NOT overdue in UTC, but the local wall-clock falls BEFORE the cut-off
    for _ in range(plan["decoy"]):
        off, gap = DECOY_SPEC[di]; di += 1
        rows.append((cls, cut + gap, off, "false"))

    # age exactly equal to the window. The second one is written in +05:30 so
    # that it is only recognisable as the boundary after normalising to UTC.
    for k in range(plan["edge"]):
        rows.append((cls, cut, "+00:00" if cls == "txn_log" else "+05:30", "false"))

    for kind, n in (("recent", plan["recent"]), ("rhold", plan["rhold"])):
        for _ in range(n):
            lo = max(cut + MARGIN, datetime(2019, 6, 1, tzinfo=timezone.utc))
            inst = draw(lo, LATEST)
            rows.append((cls, inst, rng.choices(OFFSETS, OFF_W)[0],
                         "true" if kind == "rhold" else "false"))

# One pinned audit-trail record, a few weeks inside a 2,555-day window: the
# oldest class in the inventory looks like the risky one and carries no exposure
# at all. Pinned rather than drawn so the "oldest record" figure is stable.
rows.append(("audit_trail", datetime(2019, 5, 12, 9, 14, 0, tzinfo=timezone.utc),
             "+00:00", "false"))

# Inventory exports arrive in no meaningful order.
rng.shuffle(rows)

with open("records.csv", "w", newline="", encoding="utf-8") as fh:
    wr = csv.writer(fh, lineterminator="\n")
    wr.writerow(["record_id", "class", "created_at", "legal_hold"])
    for i, (cls, inst, off, hold) in enumerate(rows, start=1):
        wr.writerow([f"REC-{i:05d}", cls, fmt(inst, off), hold])

print(f"wrote records.csv: {len(rows)} rows")

POLICY = """# Records Retention Schedule — RS-2026.1

Owner: Data Governance Office
Status: in force
Effective: 2026-01-15
Supersedes: RS-2025.3

## 1. Scope

This schedule governs every record class held in the platform record inventory.
Backup snapshots and disaster-recovery copies are out of scope; they are governed
by BR-2024.2 and must not be included in any figure reported under this schedule.

## 2. How the windows are applied

2.1  Compliance is assessed at a fixed instant, not continuously. For the current
     reporting cycle that instant — the snapshot instant — is
     **2026-04-01T00:00:00Z**. Every determination made under this schedule is
     made as of that instant. It does not move with the wall clock of whoever is
     running the assessment.

2.2  Retention is measured from the record's creation timestamp. Inventory
     timestamps are written by the originating region and carry that region's UTC
     offset. All arithmetic under this schedule is performed in Coordinated
     Universal Time, so a creation timestamp must be normalised to UTC before its
     age is computed. Comparing the local wall-clock portion of a timestamp
     against a UTC cut-off is not a valid determination and has previously
     produced both false positives and false negatives in the same cycle.

2.3  Windows are stated in calendar days, counted from creation to the snapshot
     instant. A record becomes eligible for destruction once its age EXCEEDS its
     window. A record whose age equals its window exactly is not yet eligible and
     is carried into the next cycle.

2.4  A record under legal hold is exempt from scheduled destruction for as long as
     the hold is in force, whatever its age. A hold neither extends nor shortens
     the underlying window: on release, the record is assessed against its
     original creation timestamp. Held records are reported separately and must
     never appear on a destruction list.

## 3. Class windows

### 3.1 Transaction logs — `txn_log`

Retention: **90 days**. Operational payment and ledger event logs emitted by the
transaction pipeline.

### 3.2 Support correspondence — `support_corr`

Retention: **540 days**. Inbound and outbound customer support messages,
including attachments and internal notes on the thread.

### 3.3 Marketing contact records — `marketing_contact`

Retention: **1,095 days** (36 months). Consent records, campaign membership and
suppression-list entries.

### 3.4 Audit trail events — `audit_trail`

Retention: **2,555 days** (7 years). Authentication, authorisation and
administrative action events. This is a statutory minimum and must not be
shortened for storage reasons.

### 3.5 Recruitment applicant files — `hr_applicant`

Retention: **730 days**. Applications, interview notes and assessment scores for
candidates not subsequently employed.

### 3.6 Session replay bundles — `session_replay`

Session replay bundles are a derived artefact of a support interaction and are
not separately scheduled: a bundle is retained for the same period as the support
correspondence it was captured alongside, and is assessed under §3.2. Bundles are
not un-scheduled, are not indefinitely retained, and are not exempt from §2.4.

## 4. Reporting

Each cycle the Data Governance Office reports, per class: the number of records
past window at the snapshot instant, the number of those withheld under §2.4, and
the resulting destruction list. Over-statement of the backlog is a reportable
control failure in its own right, on the same footing as failure to destroy.
"""
open("policy.md", "w", encoding="utf-8").write(POLICY)
print("wrote policy.md")
BUILD


# ─────────────────────────────────────────────────────────────────────────────
# READ-BACK. Shares no state with the builder: it re-opens records.csv and
# policy.md from disk, re-derives the windows by parsing the markdown (including
# proving that §3.6 states no number of its own), and reports only what it finds.
# GROUND_TRUTH.md is whatever this prints.
# ─────────────────────────────────────────────────────────────────────────────
python3 - <<'READBACK'
import csv, re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

policy = open("policy.md", encoding="utf-8").read()

# ── snapshot instant, straight out of the policy text ────────────────────────
m = re.search(r"\*\*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\*\*", policy)
SNAPSHOT = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

# ── class entries: code, and the window if the entry states one ──────────────
entries = re.findall(r"### 3\.\d+ (.+?) — `([a-z_]+)`\n(.*?)(?=\n### |\n## )",
                     policy, re.S)
stated, unstated, label = {}, [], {}
for name, code, body in entries:
    label[code] = name
    mm = re.search(r"Retention:\s*\*\*([\d,]+) days\*\*", body)
    if mm:
        stated[code] = int(mm.group(1).replace(",", ""))
    else:
        unstated.append((code, body.strip()))

# resolve the unstated entry by following its cross-reference
resolved = {}
for code, body in unstated:
    ref = re.search(r"assessed under §(3\.\d+)", body).group(1)
    target = re.search(r"### " + re.escape(ref) + r" .+?`([a-z_]+)`", policy).group(1)
    resolved[code] = (ref, target, stated[target])

WINDOW = dict(stated)
WINDOW.update({c: w for c, (_, _, w) in resolved.items()})
CUTOFF = {c: SNAPSHOT - timedelta(days=d) for c, d in WINDOW.items()}

# ── the inventory ────────────────────────────────────────────────────────────
recs = list(csv.DictReader(open("records.csv", encoding="utf-8")))
for r in recs:
    r["utc"] = datetime.fromisoformat(r["created_at"]).astimezone(timezone.utc)
    # the invalid determination §2.2 warns about: drop the offset, keep the
    # wall-clock digits, and pretend they are UTC
    r["naive"] = datetime.fromisoformat(r["created_at"]).replace(tzinfo=timezone.utc)
    r["hold"] = r["legal_hold"] == "true"
    r["cut"] = CUTOFF[r["class"]]
    r["overdue"] = r["utc"] < r["cut"]                 # §2.3: age must EXCEED
    r["naive_overdue"] = r["naive"] < r["cut"]

by_cls = defaultdict(list)
for r in recs:
    by_cls[r["class"]].append(r)
ORDER = ["txn_log", "support_corr", "marketing_contact", "hr_applicant",
         "session_replay", "audit_trail"]

def n(pred, rows=recs):
    return sum(1 for r in rows if pred(r))

out = []
w = out.append
w("# GROUND_TRUTH.md — retention-purge-gap")
w("")
w("Everything below was read **back out of the built artefacts** by the read-back")
w("stage of `build_fixture.sh` (`bash build_fixture.sh` regenerates this file).")
w("`records.csv` is re-parsed with the `csv` module and every timestamp is")
w("normalised with `datetime.fromisoformat(...).astimezone(utc)`; the windows are")
w("re-derived by regex out of `policy.md`, including following the cross-reference")
w("in §3.6. No value here comes from the builder's in-memory state.")
w("")

w("## Shape")
w("")
w(f"- `records.csv` rows (excluding header): **{len(recs)}**")
w("- columns: `record_id`, `class`, `created_at`, `legal_hold`")
w(f"- `record_id` range: `{min(r['record_id'] for r in recs)}` .. `{max(r['record_id'] for r in recs)}`")
w(f"- classes: **{len(by_cls)}** — " + ", ".join(f"`{c}` ({len(by_cls[c])})" for c in ORDER))
w(f"- `legal_hold` is true on **{n(lambda r: r['hold'])}** records, false on "
  f"**{n(lambda r: not r['hold'])}**")
w(f"- distinct UTC offsets present in `created_at`: " +
  ", ".join(f"`{o}`" for o in sorted({r['created_at'][-6:] for r in recs})))
w(f"- records written with a non-UTC offset: **{n(lambda r: r['created_at'][-6:] != '+00:00')}**")
w(f"- earliest creation instant (UTC): **{min(r['utc'] for r in recs).isoformat()}**; "
  f"latest: **{max(r['utc'] for r in recs).isoformat()}**")
w("")
w(f"- snapshot instant parsed out of `policy.md` §2.1: **{SNAPSHOT.isoformat()}**")
w("- `policy.md` states this instant explicitly, so nothing in the assessment depends")
w("  on the current date")
w("")

w("## Window resolution")
w("")
w("| class | policy section | window (days) | states its own figure? | cut-off (UTC) |")
w("|---|---|---:|---|---|")
for c in ORDER:
    sec = re.search(r"### (3\.\d+) .+?`" + c + r"`", policy).group(1)
    own = "yes" if c in stated else f"**no — by reference to §{resolved[c][0]}**"
    w(f"| `{c}` | §{sec} | {WINDOW[c]:,} | {own} | {CUTOFF[c].isoformat()} |")
w("")
for c, (ref, target, val) in resolved.items():
    sec = re.search(r"### (3\.\d+) .+?`" + c + r"`", policy).group(1)
    w(f"- `{c}` (§{sec}) contains **no digit sequence of the form `N days`** — the read-back's")
    w(f"  `Retention: **N days**` regex returns nothing for it. Its window comes only from")
    w(f"  the sentence \"assessed under §{ref}\", which resolves to `{target}` and")
    w(f"  therefore **{val} days**. A per-class lookup keyed on a stated figure drops this")
    w(f"  class silently.")
    w(f"- `session_replay` holds **{len(by_cls[c])}** records, "
      f"**{len(by_cls[c])/len(recs)*100:.1f}%** of the inventory.")
w("")

w("## Layer 1 — past window at the snapshot instant (UTC, §2.2 and §2.3 applied)")
w("")
w("| class | records | past window | of those, held | eligible for destruction |")
w("|---|---:|---:|---:|---:|")
tot = dict(rec=0, od=0, held=0, el=0)
per = {}
for c in ORDER:
    rows = by_cls[c]
    od = n(lambda r: r["overdue"], rows)
    hd = n(lambda r: r["overdue"] and r["hold"], rows)
    per[c] = (od, hd, od - hd)
    tot["rec"] += len(rows); tot["od"] += od; tot["held"] += hd; tot["el"] += od - hd
    w(f"| `{c}` | {len(rows)} | **{od}** | {hd} | **{od-hd}** |")
w(f"| **total** | **{tot['rec']}** | **{tot['od']}** | **{tot['held']}** | **{tot['el']}** |")
w("")
w(f"- records past their window at the snapshot instant: **{tot['od']}**")
w(f"- of those, under legal hold and therefore exempt under §2.4: **{tot['held']}**")
w(f"- **eligible for destruction: {tot['el']}**")
w(f"- largest single class exposure: `txn_log` at **{per['txn_log'][0]}** past window, "
  f"**{per['txn_log'][2]}** eligible")
w(f"- `audit_trail` exposure: **{per['audit_trail'][0]}**. Its oldest record is "
  f"**{min(r['utc'] for r in by_cls['audit_trail']).isoformat()}**, which is "
  f"**{(min(r['utc'] for r in by_cls['audit_trail']) - CUTOFF['audit_trail']).days}** days "
  f"inside a {WINDOW['audit_trail']:,}-day window, so the oldest class in the inventory "
  f"carries no backlog at all")
w("")

w("## Layer 2a — what the missed class costs")
w("")
sr_od, sr_hd, sr_el = per["session_replay"]
w(f"- `session_replay` past window: **{sr_od}**; held: **{sr_hd}**; eligible: **{sr_el}**")
w(f"- an assessment that resolves only the five classes with a stated figure reports "
  f"**{tot['od'] - sr_od}** past window and **{tot['el'] - sr_el}** eligible")
w(f"- the gap is **{sr_od}** records past window "
  f"({sr_od/tot['od']*100:.1f}% of the true backlog) and **{sr_el}** eligible records "
  f"({sr_el/tot['el']*100:.1f}% of the true destruction list)")
w("")

w("## Layer 2b — the legal-hold exemption, and the over-correction inside it")
w("")
w(f"- `legal_hold` = true: **{n(lambda r: r['hold'])}** records")
w(f"- of those, past window (genuine exemptions): **{n(lambda r: r['hold'] and r['overdue'])}**")
w(f"- of those, inside their window (exempt nothing — they were never on the list): "
  f"**{n(lambda r: r['hold'] and not r['overdue'])}**")
w(f"- so the correct subtraction from {tot['od']} is **{tot['held']}**, giving "
  f"**{tot['el']}**. Subtracting every held record instead gives "
  f"**{tot['od'] - n(lambda r: r['hold'])}**, which is wrong by "
  f"**{n(lambda r: r['hold'] and not r['overdue'])}**.")
w("- held-and-overdue records by class: " +
  ", ".join(f"`{c}` {per[c][1]}" for c in ORDER if per[c][1]))
w("")
held_od = sorted((r["record_id"], r["class"]) for r in recs if r["hold"] and r["overdue"])
w("- the held-and-overdue record ids: " + ", ".join(f"`{i}`" for i, _ in held_od))
w("")

w("## Decoy — records that are overdue only if the offsets are dropped (§2.2)")
w("")
dec = sorted([r for r in recs if r["naive_overdue"] and not r["overdue"]],
             key=lambda r: r["record_id"])
w(f"count: **{len(dec)}**")
w("")
w("| record_id | class | created_at (as written) | UTC instant | class cut-off | verdict |")
w("|---|---|---|---|---|---|")
for r in dec:
    w(f"| `{r['record_id']}` | `{r['class']}` | `{r['created_at']}` | "
      f"{r['utc'].isoformat()} | {r['cut'].isoformat()} | inside window — **do not purge** |")
w("")
w("- every one of these carries a negative offset, so its UTC instant is LATER than its")
w("  wall-clock digits. Treating the digits as UTC puts it on the overdue side of the")
w("  cut-off by a few hours.")
w(f"- by class: " + ", ".join(f"`{c}` {sum(1 for r in dec if r['class']==c)}"
                              for c in ORDER if any(r['class']==c for r in dec)))
w(f"- an assessment that ignores the offsets reports "
  f"**{n(lambda r: r['naive_overdue'])}** records past window instead of **{tot['od']}**")
w("")

rev = sorted([r for r in recs if r["overdue"] and not r["naive_overdue"]],
             key=lambda r: r["record_id"])
w("## Decoy, other direction — overdue records that a wall-clock read misses")
w("")
w(f"count: **{len(rev)}**")
w("")
w("| record_id | class | created_at (as written) | UTC instant | class cut-off | verdict |")
w("|---|---|---|---|---|---|")
for r in rev:
    w(f"| `{r['record_id']}` | `{r['class']}` | `{r['created_at']}` | "
      f"{r['utc'].isoformat()} | {r['cut'].isoformat()} | past window — **purge** |")
w("")
w("- these carry positive offsets, so the UTC instant is EARLIER than the wall-clock")
w("  digits: the record is overdue while the digits say it is not. None of them is under")
w(f"  legal hold, so all **{len(rev)}** belong on the destruction list.")
w(f"- net effect of dropping the offsets: +{len(dec)} false positives and "
  f"-{len(rev)} false negatives, i.e. **{n(lambda r: r['naive_overdue'])}** reported "
  f"against a true **{tot['od']}**")
w("")

w("## Edge — age exactly equal to the window (§2.3)")
w("")
edge = sorted([r for r in recs if r["utc"] == r["cut"]], key=lambda r: r["record_id"])
w(f"count: **{len(edge)}**")
w("")
for r in edge:
    w(f"- `{r['record_id']}` (`{r['class']}`): written `{r['created_at']}`, UTC "
      f"{r['utc'].isoformat()}, cut-off {r['cut'].isoformat()} — age is exactly "
      f"{WINDOW[r['class']]:,} days, so it does not EXCEED the window and is **not yet "
      f"eligible**")
w("")
w("- a `<=` comparison instead of `<` puts both of these on the destruction list, giving "
  f"**{tot['el'] + len(edge)}** instead of **{tot['el']}**")
w("")

w("## The wrong answers, and what each one reports")
w("")
naive_cls = sum(1 for r in recs if r["overdue"] and r["class"] != "session_replay")
w("| approach | records past window | eligible for destruction |")
w("|---|---:|---:|")
w(f"| per-class lookup on stated figures only, offsets ignored, all holds subtracted | "
  f"{sum(1 for r in recs if r['naive_overdue'] and r['class'] != 'session_replay')} | "
  f"{sum(1 for r in recs if r['naive_overdue'] and r['class'] != 'session_replay' and not r['hold'])} |")
w(f"| all six windows resolved, offsets ignored | {n(lambda r: r['naive_overdue'])} | "
  f"{n(lambda r: r['naive_overdue'] and not r['hold'])} |")
w(f"| all six windows resolved, UTC applied, every hold subtracted | {tot['od']} | "
  f"{tot['od'] - n(lambda r: r['hold'])} |")
w(f"| **correct** | **{tot['od']}** | **{tot['el']}** |")
w("")

w("## Numbers that appear in no claim")
w("")
w("Individual creation timestamps of ordinary records, the per-class recent/hold filler")
w("counts and the offset weighting are not asserted anywhere. Only the per-class")
w("totals, the four named record groups above and the id lists are.")

open("GROUND_TRUTH.md", "w", encoding="utf-8").write("\n".join(out) + "\n")
print("wrote GROUND_TRUTH.md")
READBACK

python3 build_operational_fixture.py
bash build_repo_fixture.sh
python3 verify_fixture.py > GROUND_TRUTH.md
echo "wrote GROUND_TRUTH.md from SQL, Git and log read-back"

echo "--- sizes ---"
wc -c records.csv policy.md retention.sql logs/*.log bundles/*.bundle GROUND_TRUTH.md
echo "--- checksums ---"
sha256sum records.csv policy.md retention.sql logs/*.log bundles/*.bundle GROUND_TRUTH.md
