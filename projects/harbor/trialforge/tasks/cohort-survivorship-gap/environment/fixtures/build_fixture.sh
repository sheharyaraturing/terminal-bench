#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# build_fixture.sh — cohort-survivorship-gap
#
# Emits, into the directory this script lives in:
#   extra.sql        CREATE TABLE + INSERTs for THREE NEW tables:
#                      cohort_enrolment   one row per enrolled subject
#                      cohort_visit_log   one row per subject per scheduled visit
#                      cohort_outcome     one row per subject WITH a final score,
#                                         which is not the same set as "completed"
#   GROUND_TRUTH.md  written by the READ-BACK STAGE at the bottom of this file,
#                    which executes extra.sql into a SCRATCH database and derives
#                    every asserted number with SQL against that database.
#
# It never touches the eight tables baked into the base image. The SQL contains
# no DROP, ALTER, UPDATE or DELETE — the read-back stage asserts that.
#
# DETERMINISM: the only entropy source is random.Random(90210), consumed in one
# fixed pass. Normal deviates are built by hand from three uniforms
# (Irwin-Hall), not from random.gauss, so the output does not depend on the
# CPython version's gaussian implementation or its internal cache. Verify with:
#     sha256sum extra.sql
#
# Run:  bash build_fixture.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

python3 - <<'BUILD'
import random
from datetime import date, timedelta

rng = random.Random(90210)

def z():
    """Unit-variance deviate from three uniforms. Version-independent."""
    return (rng.random() + rng.random() + rng.random() - 1.5) / 0.5

def score(mu, sd):
    return max(0.0, min(100.0, round(mu + sd * z(), 1)))

N = 180
ARMS = ("INTERVENTION", "CONTROL")
SITES = ("SITE-01", "SITE-02", "SITE-03", "SITE-04")
VISITS = ((1, "BASELINE", 0), (2, "WEEK_4", 28), (3, "WEEK_12", 84),
          (4, "END_OF_STUDY", 168))

# ── Allocation ──────────────────────────────────────────────────────────────
# Arm and site are assigned jointly so the marginals are exact: 90 per arm, 45
# per site. Sites 1-2 get 23 intervention / 22 control, sites 3-4 the reverse.
ARM_BY_SITE = {"SITE-01": 23, "SITE-02": 23, "SITE-03": 22, "SITE-04": 22}

subjects = []          # (subject_id, arm, site)
sid = 0
for site in SITES:
    n_int = ARM_BY_SITE[site]
    cell = ["INTERVENTION"] * n_int + ["CONTROL"] * (45 - n_int)
    rng.shuffle(cell)
    for arm in cell:
        sid += 1
        subjects.append([f"SUBJ-{sid:03d}", arm, site])
subjects.sort(key=lambda r: r[0])

assert sum(1 for s in subjects if s[1] == "INTERVENTION") == 90
assert sum(1 for s in subjects if s[1] == "CONTROL") == 90

# ── Who drops out ───────────────────────────────────────────────────────────
# 46 dropouts, deliberately NOT missing at random: 34 in the intervention arm
# against 12 in the control arm. Chosen stratified by site so the site marginals
# stay flat (12, 12, 11, 11) and "it is a site effect" is refutable from the
# data rather than from assertion.
DROPOUTS_PER_CELL = {
    ("INTERVENTION", "SITE-01"): 9, ("INTERVENTION", "SITE-02"): 9,
    ("INTERVENTION", "SITE-03"): 8, ("INTERVENTION", "SITE-04"): 8,
    ("CONTROL", "SITE-01"): 3, ("CONTROL", "SITE-02"): 3,
    ("CONTROL", "SITE-03"): 3, ("CONTROL", "SITE-04"): 3,
}
dropouts = set()
for (arm, site), k in sorted(DROPOUTS_PER_CELL.items()):
    pool = sorted(s[0] for s in subjects if s[1] == arm and s[2] == site)
    dropouts.update(rng.sample(pool, k))
assert len(dropouts) == 46

completers = [s[0] for s in subjects if s[0] not in dropouts]
assert len(completers) == 134

# ── Attendance patterns ─────────────────────────────────────────────────────
# Two deliberate wrinkles, both about how "completed" is computed:
#   * 6 COMPLETERS miss one intermediate visit but do attend the end-of-study
#     visit. Counting subjects with four attended visits therefore undercounts
#     completers by 6.
#   * 6 DROPOUTS attend intermittently, so their last attended visit is not the
#     same as their count of attended visits.
gap_completers = sorted(rng.sample(completers, 6))
intermittent_dropouts = sorted(rng.sample(sorted(dropouts), 6))

def attendance(subject_id):
    """Returns a 4-tuple of 0/1 for visits 1..4."""
    if subject_id in dropouts:
        if subject_id in intermittent_dropouts:
            return (1, 0, 1, 0)
        last = rng.choice([1, 2, 3])
        return tuple(1 if v <= last else 0 for v in (1, 2, 3, 4))
    if subject_id in gap_completers:
        missed = rng.choice([2, 3])
        return tuple(0 if v == missed else 1 for v in (1, 2, 3, 4))
    return (1, 1, 1, 1)

# ── Trajectories ────────────────────────────────────────────────────────────
# Completers climb toward an arm-specific final level. Dropouts sit on a low
# plateau and never climb — they are the poor responders, which is what makes
# the survivorship bias directional.
LEVEL = {"INTERVENTION": (65.0, 8.0), "CONTROL": (61.0, 8.0)}
PLATEAU = {"INTERVENTION": (42.0, 7.0), "CONTROL": (50.0, 7.0)}
CLIMB = {1: 0.64, 2: 0.79, 3: 0.91, 4: 0.98}

enrol_rows, visit_rows, outcome_rows = [], [], []
START = date(2023, 1, 9)

for subject_id, arm, site in subjects:
    enrolled = START + timedelta(days=rng.randrange(0, 168))
    enrol_rows.append((subject_id, arm, enrolled.isoformat(), site))

    att = attendance(subject_id)
    is_dropout = subject_id in dropouts
    if is_dropout:
        mu, sd = PLATEAU[arm]
        level = score(mu, sd)
    else:
        mu, sd = LEVEL[arm]
        level = score(mu, sd)

    for (visit_no, visit_type, offset), attended in zip(VISITS, att):
        vdate = (enrolled + timedelta(days=offset + rng.randrange(0, 6))).isoformat()
        if not attended:
            visit_rows.append((subject_id, visit_no, visit_type, vdate, 0, None))
            continue
        if is_dropout:
            interim = score(level, 3.0)          # flat plateau, no climb
        else:
            interim = score(level * CLIMB[visit_no], 3.0)
        visit_rows.append((subject_id, visit_no, visit_type, vdate, 1, interim))

    if not is_dropout:
        assessed = (enrolled + timedelta(days=170 + rng.randrange(0, 10))).isoformat()
        outcome_rows.append((subject_id, assessed, score(level, 2.0)))

# ── The decoy: one genuine completer with no outcome row ─────────────────────
# A data-entry failure, not a withdrawal. This subject attended every scheduled
# visit including the end-of-study visit, so counting "enrolled subjects with no
# outcome row" as dropouts overstates the dropout count by exactly one.
missing_outcome = sorted(
    s for s in completers
    if s not in gap_completers
    and next(x[1] for x in subjects if x[0] == s) == "CONTROL"
)[4]
outcome_rows = [r for r in outcome_rows if r[0] != missing_outcome]

assert len(outcome_rows) == 133, len(outcome_rows)

# ── Emit extra.sql ──────────────────────────────────────────────────────────
def lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, str):
        return "'" + v.replace("'", "''") + "'"
    return repr(v)

def batched(rows, table, columns, per=20):
    out = []
    for start in range(0, len(rows), per):
        chunk = rows[start:start + per]
        values = ",\n  ".join("(" + ", ".join(lit(v) for v in row) + ")"
                              for row in chunk)
        out.append(f"INSERT INTO {table} ({', '.join(columns)}) VALUES\n  {values};")
    return "\n".join(out)

with open("extra.sql", "w", encoding="utf-8") as fh:
    fh.write("""\
-- cohort-survivorship-gap fixture.
--
-- Creates THREE NEW tables and nothing else. There is no DROP, ALTER, UPDATE or
-- DELETE anywhere in this file: the eight tables baked into the base image are
-- shared with other tasks in the suite and are left exactly as they are.
--
-- cohort_enrolment  one row per enrolled subject. This is the denominator.
-- cohort_visit_log  one row per subject per SCHEDULED visit, attended or not.
--                   attended = 1 at visit_type 'END_OF_STUDY' is what makes a
--                   subject a completer; interim_score is NULL when a visit was
--                   not attended.
-- cohort_outcome    one row per subject who has a recorded final score. That is
--                   NOT the same set as the completers.
--
-- Column types follow the baked convention: TEXT unless every value parses as
-- INTEGER or REAL.

CREATE TABLE IF NOT EXISTS cohort_enrolment (
  subject_id  TEXT,
  arm         TEXT,
  enrolled_at TEXT,
  site        TEXT
);

CREATE TABLE IF NOT EXISTS cohort_visit_log (
  subject_id   TEXT,
  visit_no     INTEGER,
  visit_type   TEXT,
  visit_date   TEXT,
  attended     INTEGER,
  interim_score REAL
);

CREATE TABLE IF NOT EXISTS cohort_outcome (
  subject_id    TEXT,
  assessed_at   TEXT,
  endpoint_score REAL
);

""")
    fh.write(batched(enrol_rows, "cohort_enrolment",
                     ("subject_id", "arm", "enrolled_at", "site")))
    fh.write("\n\n")
    fh.write(batched(visit_rows, "cohort_visit_log",
                     ("subject_id", "visit_no", "visit_type", "visit_date",
                      "attended", "interim_score"), per=12))
    fh.write("\n\n")
    fh.write(batched(outcome_rows, "cohort_outcome",
                     ("subject_id", "assessed_at", "endpoint_score")))
    fh.write("\n")

print("built extra.sql: %d enrolment, %d visit, %d outcome rows"
      % (len(enrol_rows), len(visit_rows), len(outcome_rows)))
BUILD

# ── READ-BACK STAGE ─────────────────────────────────────────────────────────
# Independent of the builder. It executes extra.sql into a scratch database and
# derives every asserted number with SQL against that database. GROUND_TRUTH.md
# is whatever this stage prints. No value comes from the builder's memory.
python3 - <<'READBACK'
import os, re, sqlite3, tempfile

sql = open("extra.sql", encoding="utf-8").read()

# Safety property, checked against the text that will actually be piped into
# /data/db/turing.db at image build time.
# Strip -- comments first: the file's own header names the statements it does
# not contain, and matching that text would be a false positive.
statements = "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())
forbidden = sorted({kw for kw in ("DROP", "ALTER", "UPDATE", "DELETE", "REPLACE",
                                  "ATTACH", "PRAGMA", "VACUUM")
                    if re.search(r"\b" + kw + r"\b", statements, re.I)})
created = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", sql)

db = os.path.join(tempfile.mkdtemp(), "scratch.db")
con = sqlite3.connect(db)
con.executescript(sql)
q = lambda s, *a: con.execute(s, a).fetchall()
one = lambda s, *a: con.execute(s, a).fetchone()[0]

def pct(n, d):
    return round(100.0 * n / d, 1)

out = []
w = out.append
w("# GROUND_TRUTH.md — cohort-survivorship-gap")
w("")
w("Every number below was read **back out of the built artefact** by the read-back")
w("stage of `build_fixture.sh` (`bash build_fixture.sh` regenerates this file).")
w("`extra.sql` was executed into a scratch SQLite database and every figure here")
w("was then obtained with SQL against that database. Nothing comes from the")
w("builder's in-memory state.")
w("")

# ── safety ──
w("## Safety of the injection")
w("")
w(f"- tables created: {', '.join('`'+t+'`' for t in created)}")
w(f"- forbidden statements found in `extra.sql`: "
  f"{'**none**' if not forbidden else '**' + ', '.join(forbidden) + '**'}")
w(f"- `extra.sql` size: **{len(sql.encode()):,} bytes**")
w("")
w("The file only creates new tables and inserts into them, so the eight baked")
w("tables in `turing.db` are untouched.")
w("")

# ── shape ──
n_enrol = one("SELECT COUNT(*) FROM cohort_enrolment")
n_visit = one("SELECT COUNT(*) FROM cohort_visit_log")
n_out = one("SELECT COUNT(*) FROM cohort_outcome")
w("## Shape")
w("")
w(f"- `cohort_enrolment` rows: **{n_enrol}** (one per enrolled subject)")
w(f"- `cohort_visit_log` rows: **{n_visit}** "
  f"(**{one('SELECT COUNT(DISTINCT visit_no) FROM cohort_visit_log')}** scheduled visits "
  f"per subject: " + ", ".join(f"{r[0]} `{r[1]}`" for r in
                               q("SELECT visit_no, visit_type FROM cohort_visit_log "
                                 "GROUP BY visit_no, visit_type ORDER BY visit_no")) + ")")
w(f"- `cohort_outcome` rows: **{n_out}**")
w("- subjects per arm: " + ", ".join(
    f"{r[0]} **{r[1]}**" for r in
    q("SELECT arm, COUNT(*) FROM cohort_enrolment GROUP BY arm ORDER BY arm")))
w("- subjects per site: " + ", ".join(
    f"{r[0]} {r[1]}" for r in
    q("SELECT site, COUNT(*) FROM cohort_enrolment GROUP BY site ORDER BY site")))
w(f"- enrolment window: {one('SELECT MIN(enrolled_at) FROM cohort_enrolment')} to "
  f"{one('SELECT MAX(enrolled_at) FROM cohort_enrolment')}")
w(f"- subjects in `cohort_outcome` that are not in `cohort_enrolment`: "
  f"**{one('SELECT COUNT(*) FROM cohort_outcome o WHERE o.subject_id NOT IN (SELECT subject_id FROM cohort_enrolment)')}**")
w("")

# ── completion, defined from the visit log ──
con.executescript("""
CREATE VIEW completer AS
  SELECT DISTINCT subject_id FROM cohort_visit_log
  WHERE visit_type = 'END_OF_STUDY' AND attended = 1;
CREATE VIEW attended_count AS
  SELECT subject_id, SUM(attended) AS n FROM cohort_visit_log GROUP BY subject_id;
CREATE VIEW last_seen AS
  SELECT subject_id, MAX(visit_no) AS visit_no FROM cohort_visit_log
  WHERE attended = 1 GROUP BY subject_id;
CREATE VIEW locf AS
  SELECT e.subject_id, e.arm,
         COALESCE(o.endpoint_score, v.interim_score) AS value,
         CASE WHEN o.subject_id IS NULL THEN 'carried forward' ELSE 'endpoint' END AS origin
  FROM cohort_enrolment e
  LEFT JOIN cohort_outcome o ON o.subject_id = e.subject_id
  LEFT JOIN last_seen ls ON ls.subject_id = e.subject_id
  LEFT JOIN cohort_visit_log v
         ON v.subject_id = e.subject_id AND v.visit_no = ls.visit_no;
""")

n_completers = one("SELECT COUNT(*) FROM completer")
n_dropouts = n_enrol - n_completers
n_all_four = one("SELECT COUNT(*) FROM attended_count WHERE n = 4")

w("## Layer 1 — the outcome table covers completers, not enrolments")
w("")
w(f"- subjects with an outcome row: **{n_out}** of **{n_enrol}** enrolled = "
  f"**{pct(n_out, n_enrol)}%**")
w(f"- subjects an inner join between enrolment and outcome silently drops: "
  f"**{n_enrol - n_out}**")
w(f"- retention read off the inner-joined set alone: "
  f"**{pct(n_out, n_out)}%** — every row in that set has an outcome by")
w("  construction, so the join makes the metric unfalsifiable rather than good")
w("")
w("Per-arm outcome coverage:")
w("")
w("| arm | enrolled | with an outcome row | coverage |")
w("|---|---:|---:|---:|")
for arm, n, k in q("""SELECT e.arm, COUNT(*),
                             SUM(CASE WHEN o.subject_id IS NULL THEN 0 ELSE 1 END)
                      FROM cohort_enrolment e
                      LEFT JOIN cohort_outcome o ON o.subject_id = e.subject_id
                      GROUP BY e.arm ORDER BY e.arm"""):
    w(f"| {arm} | {n} | {k} | {pct(k, n)}% |")
w("")
w("## Completion as the visit log defines it")
w("")
w("A subject completed if the visit log records `attended = 1` at the")
w("`END_OF_STUDY` visit.")
w("")
w(f"- completers: **{n_completers}**")
w(f"- dropouts (enrolled, did not attend the end-of-study visit): **{n_dropouts}**")
w(f"- true completion rate: **{n_completers}/{n_enrol} = {pct(n_completers, n_enrol)}%**")
w("")
w(f"- subjects with all four visits attended: **{n_all_four}**. Counting completers")
w(f"  that way misses **{n_completers - n_all_four}** subjects who skipped one")
w("  intermediate visit and still attended the end-of-study visit, and would give")
w(f"  **{pct(n_all_four, n_enrol)}%** instead.")
w(f"- dropouts whose last attended visit is later than their attended-visit count")
w("  implies (intermittent attendance): **"
  + str(one("""SELECT COUNT(*) FROM last_seen ls JOIN attended_count ac
               USING (subject_id)
               WHERE ls.subject_id NOT IN (SELECT subject_id FROM completer)
                 AND ls.visit_no <> ac.n""")) + "**")
w("")
w("| arm | enrolled | completers | dropouts | completion rate | dropout rate |")
w("|---|---:|---:|---:|---:|---:|")
arm_stats = {}
for arm, n in q("SELECT arm, COUNT(*) FROM cohort_enrolment GROUP BY arm ORDER BY arm"):
    c = one("""SELECT COUNT(*) FROM cohort_enrolment e JOIN completer c
               USING (subject_id) WHERE e.arm = ?""", arm)
    arm_stats[arm] = (n, c, n - c)
    w(f"| {arm} | {n} | {c} | {n - c} | {pct(c, n)}% | {pct(n - c, n)}% |")
w("")

# ── Layer 2: non-random dropout ──
w("## Layer 2 — the dropouts are not missing at random")
w("")
i_n, i_c, i_d = arm_stats["INTERVENTION"]
c_n, c_c, c_d = arm_stats["CONTROL"]
w(f"- of the **{n_dropouts}** dropouts, **{i_d}** are in INTERVENTION and "
  f"**{c_d}** in CONTROL")
w(f"- dropout rates: INTERVENTION **{pct(i_d, i_n)}%** against CONTROL "
  f"**{pct(c_d, c_n)}%** — a differential of "
  f"**{round(pct(i_d, i_n) - pct(c_d, c_n), 1)} percentage points**")
w("")
w("Dropouts by site, to test the competing explanation:")
w("")
w("| site | enrolled | dropouts | dropout rate |")
w("|---|---:|---:|---:|")
for site, n in q("SELECT site, COUNT(*) FROM cohort_enrolment GROUP BY site ORDER BY site"):
    d = one("""SELECT COUNT(*) FROM cohort_enrolment e
               WHERE e.site = ? AND e.subject_id NOT IN (SELECT subject_id FROM completer)""",
            site)
    w(f"| {site} | {n} | {d} | {pct(d, n)}% |")
w("")
w("The site marginals are flat, so a site effect does not account for the")
w("concentration. The arm marginals are not.")
w("")

# ── direction of the bias ──
w("### Direction of the bias")
w("")
drop_mean = one("""SELECT ROUND(AVG(value), 2) FROM locf
                   WHERE subject_id NOT IN (SELECT subject_id FROM completer)""")
comp_mean = one("SELECT ROUND(AVG(endpoint_score), 2) FROM cohort_outcome")
w(f"- mean last-observed score of the **{n_dropouts}** dropouts: **{drop_mean}**")
w(f"- mean endpoint score of the **{n_out}** subjects with an outcome row: "
  f"**{comp_mean}**")
w(f"- the dropouts sit **{round(comp_mean - drop_mean, 2)} points** below the")
w("  analysed set, so dropping them biases every arm mean UPWARD, and biases the")
w("  arm that lost more subjects upward by more")
w("")
w("| arm | mean last-observed score of its dropouts |")
w("|---|---:|")
for arm, m in q("""SELECT arm, ROUND(AVG(value), 2) FROM locf
                   WHERE subject_id NOT IN (SELECT subject_id FROM completer)
                   GROUP BY arm ORDER BY arm"""):
    w(f"| {arm} | {m} |")
w("")

# ── the flip ──
w("## The between-arm comparison flips")
w("")
w("### As analysed — completers with an outcome row only (the inner join)")
w("")
w("| arm | n | mean endpoint score |")
w("|---|---:|---:|")
cm = {}
for arm, n, m in q("""SELECT e.arm, COUNT(*), ROUND(AVG(o.endpoint_score), 2)
                      FROM cohort_enrolment e JOIN cohort_outcome o
                      USING (subject_id) GROUP BY e.arm ORDER BY e.arm"""):
    cm[arm] = (n, m)
    w(f"| {arm} | {n} | {m} |")
gap_c = round(cm["INTERVENTION"][1] - cm["CONTROL"][1], 2)
w("")
w(f"INTERVENTION leads CONTROL by **{gap_c} points**.")
w("")
w("### Every enrolled subject, last observation carried forward")
w("")
w("Each subject contributes their endpoint score if they have one, otherwise the")
w("interim score from their last attended visit. All "
  f"{one('SELECT COUNT(*) FROM locf WHERE value IS NOT NULL')} enrolled subjects")
w("carry a value; " +
  str(one("SELECT COUNT(*) FROM locf WHERE origin = 'carried forward'")) +
  " of them are carried forward.")
w("")
w("| arm | n | mean carried-forward score |")
w("|---|---:|---:|")
lm = {}
for arm, n, m in q("""SELECT arm, COUNT(*), ROUND(AVG(value), 2) FROM locf
                      GROUP BY arm ORDER BY arm"""):
    lm[arm] = (n, m)
    w(f"| {arm} | {n} | {m} |")
gap_l = round(lm["INTERVENTION"][1] - lm["CONTROL"][1], 2)
w("")
w(f"CONTROL leads INTERVENTION by **{abs(gap_l)} points**.")
w("")
w(f"- completers-only difference (INTERVENTION − CONTROL): **{gap_c:+.2f}**")
w(f"- carried-forward difference (INTERVENTION − CONTROL): **{gap_l:+.2f}**")
w(f"- **the sign flips**: "
  f"{'YES' if (gap_c > 0) != (gap_l > 0) else 'NO — RETUNE THE FIXTURE'}")
w(f"- total swing: **{round(gap_c - gap_l, 2)} points**")
w("")

# ── the decoy ──
w("## Decoy — a completer with no outcome row")
w("")
rows = q("""SELECT c.subject_id, e.arm, e.site,
                   (SELECT SUM(attended) FROM cohort_visit_log v
                     WHERE v.subject_id = c.subject_id),
                   (SELECT interim_score FROM cohort_visit_log v
                     WHERE v.subject_id = c.subject_id AND v.visit_type = 'END_OF_STUDY')
            FROM completer c JOIN cohort_enrolment e USING (subject_id)
            WHERE c.subject_id NOT IN (SELECT subject_id FROM cohort_outcome)
            ORDER BY c.subject_id""")
w(f"completers with no row in `cohort_outcome`: **{len(rows)}**")
for sid_, arm, site, att, last in rows:
    w("")
    w(f"- **`{sid_}`** — arm {arm}, site {site}. Attended **{att} of 4** scheduled")
    w(f"  visits including `END_OF_STUDY`, with an end-of-study interim score of")
    w(f"  **{last}**. There is no `cohort_outcome` row for this subject.")
    w("  This is a missing final assessment, not a withdrawal: the subject")
    w("  completed. Counting enrolled-minus-outcome as dropouts therefore reports")
    w(f"  **{n_enrol - n_out}** dropouts when the true figure is **{n_dropouts}**,")
    w(f"  and a completion rate of **{pct(n_out, n_enrol)}%** rather than "
      f"**{pct(n_completers, n_enrol)}%**.")
w("")
w("Consistency checks that make the decoy unambiguous:")
w("")
w(f"- dropouts holding an outcome row: **"
  + str(one("""SELECT COUNT(*) FROM cohort_outcome o
               WHERE o.subject_id NOT IN (SELECT subject_id FROM completer)""")) + "**")
w(f"- enrolled subjects with no visit-log rows at all: **"
  + str(one("""SELECT COUNT(*) FROM cohort_enrolment e
               WHERE e.subject_id NOT IN (SELECT subject_id FROM cohort_visit_log)""")) + "**")
w(f"- subjects carrying more than one outcome row: **"
  + str(one("""SELECT COUNT(*) FROM (SELECT subject_id FROM cohort_outcome
               GROUP BY subject_id HAVING COUNT(*) > 1)""")) + "**")
w(f"- visit-log rows with `attended = 0` carrying a non-null interim score: **"
  + str(one("SELECT COUNT(*) FROM cohort_visit_log WHERE attended = 0 AND interim_score IS NOT NULL"))
  + "**")
w("")
w("So the only inconsistency anywhere in the three tables is that one missing")
w("outcome row.")
w("")
w("## Numbers that appear in no claim")
w("")
w("Individual subject scores, visit dates and enrolment dates are drawn from a")
w("seeded stream and nothing about any single one of them is asserted, apart from")
w("the decoy subject named above. Only the aggregates in this file are claimed.")

open("GROUND_TRUTH.md", "w", encoding="utf-8").write("\n".join(out) + "\n")
print("wrote GROUND_TRUTH.md")
READBACK

echo "--- sizes ---"
wc -c extra.sql GROUND_TRUTH.md
echo "--- checksum ---"
sha256sum extra.sql
