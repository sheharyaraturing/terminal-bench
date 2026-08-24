# NOTES — cohort-survivorship-gap

## Premise

A Research Analyst has to defend a two-arm study's headline before a funder
review. The outcome table holds rows only for subjects who reached the end of the
study, so the natural join against the enrolment list is an inner join, the 47
missing subjects vanish before the metric is computed, and retention comes out at
100% by construction.

Layer 1 is quantifying the real figure: 133 of 180 have a final score, 73.9%.
That is one left join away and a shallow pass gets it.

The task is what is behind that. The attrition is **not** missing at random — 34
of the 46 losses are in the intervention arm against 12 in the control arm — and
the subjects who left were the poor responders, 17 points below the analysed set
at their last measurement. So the exclusion biases every arm mean upward and the
intervention arm upward by more, and the between-arm comparison **reverses**:
+3.78 points in the intervention arm's favour among finishers becomes −3.01
points against it once everyone recruited is carried in at their last
observation. The reversal was verified from the built artefact, not designed and
assumed; see below.

The gate is genuine. The direction of the bias cannot be signed, and the reversal
cannot be computed, until the dropouts have been identified — which needs the
visit log, not the outcome table. A model that stops at "retention is really
73.9%" has done none of the work the flip depends on.

Two traps sit in the arithmetic. One completer genuinely has no outcome row, so
`enrolled − outcomes` overstates the loss count by exactly one; and six
completers missed an intermediate visit, so `attended all four visits`
understates the completer count by exactly six. The two errors push in opposite
directions and neither cancels the other.

## Fixture provenance

The artefact is **synthetic and authored here**. No real trial data was used and
nothing was downloaded.

| artefact | injected as | measured size |
|---|---|---:|
| `fixtures/extra.sql` | `sqlite3 /data/db/turing.db < …` | **62,622 bytes** — 3 `CREATE TABLE IF NOT EXISTS` + batched `INSERT`s for 180 + 720 + 133 rows |
| `fixtures/GROUND_TRUTH.md` | not injected — authoring artefact | 5,669 bytes |

Build invocation:

```
bash environment/fixtures/build_fixture.sh
```

It was actually run. Determinism was verified by copying the script alone into an
empty directory, re-running it, and diffing — `extra.sql` and `GROUND_TRUTH.md`
both reproduced byte for byte:

```
extra.sql  sha256 0e3b6981d8214291346ec55f8ff25bf68cebf25619b08c40a69725e0c77005f7
```

The only entropy source is `random.Random(90210)`, consumed in one fixed pass.
Normal deviates are built by hand from three uniforms (Irwin–Hall) rather than
with `random.gauss`, so the output does not depend on the CPython version's
gaussian implementation or its internal `gauss_next` cache — that was a real
determinism hazard given the fixture is regenerated on whatever host a reviewer
happens to use. Arm and site allocation, the dropout counts per arm×site cell,
and the two attendance wrinkles are all forced to exact counts with assertions
rather than left to the RNG.

No pinned SHA — this task ships no git fixture.

`extra.sql` issues three `CREATE TABLE IF NOT EXISTS` statements plus `INSERT`s
and **nothing else**. It contains no `DROP`, `ALTER`, `UPDATE`, `DELETE`,
`REPLACE`, `ATTACH`, `PRAGMA` or `VACUUM` — the read-back stage strips `--`
comments and then scans for exactly those keywords, and reports none. The eight
tables baked into `turing.db` are shared with other tasks in the suite and are
untouched. Column types follow the baked convention: `TEXT` unless every value
parses as `INTEGER` or `REAL`, hence `visit_no` and `attended` as `INTEGER` and
`interim_score` / `endpoint_score` as `REAL` (with `interim_score` NULL on
unattended visits).

**This was tested rather than argued.** A scratch database was populated with
eight stand-in tables named after the baked eight, each with rows; a per-table
hash of DDL plus contents was taken; `extra.sql` was executed against it; the
hashes were re-taken and compared. All eight were byte-identical afterwards, and
the table count went from 8 to 11 with exactly `cohort_enrolment`,
`cohort_visit_log` and `cohort_outcome` added. That test used stand-ins, not the
real `turing.db` — see *Not verified*.

## Ground-truth read-back

`environment/fixtures/GROUND_TRUTH.md` is **generated**, not written by hand. The
read-back stage at the bottom of `build_fixture.sh` shares no state with the
builder: it executes `extra.sql` into a scratch SQLite database and derives every
asserted number with **SQL** against that database, via three views
(`completer`, `last_seen`, `locf`) defined there and not in the builder. Whatever
the stage prints is the file.

Critically, the read-back is what *verified the flip* rather than assumed it. It
computes both differences and prints the literal sign test:

```
- completers-only difference (INTERVENTION − CONTROL): **+3.78**
- carried-forward difference (INTERVENTION − CONTROL): **-3.01**
- **the sign flips**: YES
- total swing: **6.79 points**
```

The line prints `NO — RETUNE THE FIXTURE` if the two differences ever share a
sign, so a parameter change that quietly killed the flip would be visible in the
artefact rather than only in a claim that had stopped being true.

The read-back also caught two defects in its own first version, both of which
would have shipped false statements into `GROUND_TRUTH.md`:

1. **The forbidden-keyword scan matched the file's own header.** `extra.sql`
   opens with a comment saying it contains no `DROP`, `ALTER`, `UPDATE` or
   `DELETE`; the first scan read that sentence and reported all four as present.
   It now strips `--` comments before scanning, and reports none.
2. **Two of the four consistency checks were the same query** written two ways,
   so the decoy's "this is the only inconsistency" argument rested on three
   checks presented as four. Replaced with two genuinely distinct ones —
   enrolled subjects with no visit records, and subjects carrying more than one
   outcome row.

Values the read-back produced, all of which appear in `tests/reward.toml`:

- 180 enrolments, 90 per arm, 45 per site, 720 visit rows, 133 outcome rows
- 0 outcome rows for subjects not in the enrolment table
- 133/180 = 73.9% coverage; inner join drops 47; joined-set retention 100.0%
- per-arm coverage: intervention 56/90 = 62.2%, control 77/90 = 85.6%
- completers 134, dropouts 46, true completion **74.4%**
- 128 subjects attended all four visits — 6 completers skipped one intermediate
  visit; that route gives 71.1%
- 6 dropouts attended intermittently, so last-attended-visit ≠ attended count
- dropouts by arm: intervention 34 (37.8%), control 12 (13.3%), differential
  24.5 pp
- dropouts by site: 12, 12, 11, 11 of 45 each — flat
- dropouts' mean last observation 45.51 against 62.53 for the analysed set
- per-arm dropout last observation: intervention 43.2, control 52.04
- completers-only means: intervention 64.72 (n=56), control 60.94 (n=77), **+3.78**
- carried-forward means over all 180: intervention 56.59, control 59.60, **−3.01**
- swing 6.79 points, sign flips
- decoy: **`SUBJ-015`**, control arm, SITE-01, 4 of 4 visits attended, end-of-study
  measurement 47.3, no outcome row
- 0 dropouts holding an outcome row, 0 duplicate outcome rows, 0 enrolled
  subjects without visit records, 0 unattended visits carrying a score

## Difficulty design

Claim order is Layer 1 → Layer 2 → decoy → competing explanation and definition
trap: a model that stops after the retention correction banks claims 1–4 and
drops most of 5–12.

12 claims, every one at the default weight of 1.0. Dropping three gives
9/12 = **0.75**; dropping four gives 8/12 = **0.667**. The 0.75 threshold sits
on that boundary, so the intended partial pass is "corrected the retention
figure, saw that the attrition is lopsided, did not recompute the comparison or
handle the two counting traps".

The load-bearing claims and why a strong model drops them:

1. **The attrition is not missing at random** (claim 4). Requires splitting the
   46 losses by arm rather than reporting one attrition figure. The prompt asks
   whether the loss was even, so this is the most-reachable of the weighted
   claims — it is weighted because everything after it depends on it.
2. **The direction of the bias is signable** (claim 5). Requires a quantity the
   prompt never asks for: the dropouts' *scores*. The visit log carries interim
   measurements, and nothing in the prompt says to look at them. A model that
   treats the dropouts purely as missing rows can count them and never score
   them, and then cannot say which way the exclusion pushes anything.
3. **The completers-only comparison** (claim 6). Straightforward once the
   analysis set is understood, but it must be computed on the inner-joined set
   specifically — reporting it over the carried-forward set instead loses both
   this claim and the contrast claim 8 rests on.
4. **The carried-forward comparison** (claim 7). The hardest single computation
   in the task: a left join from enrolment to outcome, a `MAX(visit_no)` lookup
   over attended visits only, a join back to pick up that visit's score, and a
   coalesce. Six dropouts attended intermittently, so a model that takes the
   count of attended visits as the last visit number picks up the wrong score for
   them. The obvious shortcut — average the outcome scores and the interim scores
   together — gives a different answer.
5. **`SUBJ-015` is not a dropout** (claim 9). A completer with no outcome row is
   indistinguishable from a dropout unless the visit log is consulted, and the
   visit log is not needed for the Layer-1 figure. A model that derived
   attrition as `enrolled − outcomes` has no route to this at all.
6. **The corrected arithmetic** (claim 10). Requires carrying the single-subject
   correction through: 46 not 47, 134 not 133, 74.4% not 73.9%. Models that spot
   the case often report it as a caveat and leave the headline number
   uncorrected, which the claim explicitly fails.
7. **Completion is attendance at the final visit, not four attended visits**
   (claim 12). Six completers missed an intermediate visit. `SUM(attended) = 4`
   is the natural expression and it is wrong by six, giving 128 completers and
   71.1%. The claim fails those values by name. Note this error runs *opposite*
   to the `SUBJ-015` error, so a model making both does not accidentally land on
   the right number.
8. **The loss is not concentrated by site** (claim 11). Requires stating the
   negative — reporting 12, 12, 11 and 11 of 45 and concluding the spread is
   flat, so the loss tracks the arm rather than the site. Models asked to find a
   concentration tend to assert one, and the claim fails an answer that leaves
   the site question unmentioned rather than settling it.

Levers used, against the conventions' list: layered defects (1 — the flip is not
visible until the dropouts are identified from a table the Layer-1 figure does
not need), a claim depending on a quantity the prompt never mentions (2 — the
dropouts' interim measurements), cross-referencing (3 — enrolment against visit
log against outcomes, with no single table containing the answer), a decoy that
survives casual checking (4 — plus the four-attended-visits trap running the
other way), and a required direction and ordering (5 — which arm the bias
favours, and whether the ranking survives the method change).

**No scipy.** Every statistical claim is a rate, a count, a mean or a difference
of means. No p-value, confidence interval or test statistic is asserted anywhere,
so pandas and numpy — or plain SQL — suffice. The exposed
`mcp-code-executor_install_dependencies` is there precisely to punish a model
that decides it needs `scipy.stats` for this; the image has no egress.

## Tool surface

27 exposed, 9 needed, 6 same-server distractors, 12 off-server distractors —
distractor:needed ratio 18/9 = 2.0, holding the 1 same-server : 2 off-server
composition. 13 servers, 4 of them carrying needed tools.
`sqlite_delete_records` is not exposed.

Sharpest distractors:

- `sqlite_read_records` — an equality-only filter. It will happily fetch rows
  from any of the three tables and cannot express a left join, a `MAX(visit_no)`
  over attended visits, or a coalesce, which is the whole of the carried-forward
  step. A model that reaches for it gets rows and no answer.
- `sqlite_update_records` and `sqlite_create_record` — the mutating siblings, and
  a genuinely tempting pair here: the natural engineering instinct on finding a
  completer with no outcome row is to insert the missing row. Doing so destroys
  the decoy mid-rollout and answers a question nobody asked.
- `mcp-code-executor_install_dependencies` — the sharpest dead end in this task
  specifically, because the framing invites a significance test. No egress.
- `arxiv_search_papers`, `paper-search_search_pubmed`, `crossref_search_works` —
  a coherent near-miss cluster. This reads as a clinical-trial methodology
  question, so looking up how attrition "should" be handled is plausible, and it
  answers nothing about this cohort. Three tools that reward the wrong instinct.
- `cli-mcp-server_run_command` — no pipes and `/data` only, so it cannot even
  reach the database through `sqlite3 … | …`.
- `filesystem_read_text_file`, `desktop-commander_read_file`,
  `desktop-commander_start_search` — this task ships no data file at all, so
  every file-reading route is a dead end. `filesystem_list_directory` is in the
  needed set only because locating the database is a legitimate first step.
- `whois_whois_domain`, `ddg-search_search` — far-field.

## Realism trade

The fixture is synthetic. A real cohort would be messier: unequal arms, subjects
with partially completed final assessments rather than absent ones, protocol
deviations, competing definitions of completion in the statistical analysis plan,
withdrawal reason codes, and attrition driven by site logistics as well as by
response. The trade is deliberate and it buys full knowability — every claim
quotes a value read back out of the artefact, with no `[DERIVE]` and no guessing.

The claim structure would survive a swap to a real cohort, because each claim
describes a *pattern* rather than a particular study: an outcome table that
silently defines the analysis set, differential attrition concentrated in one
arm, dropouts who are worse than the people who stayed, a between-arm comparison
whose sign depends on the analysis population, a missing assessment that is not a
withdrawal, and a completion definition that disagrees with the obvious proxy.
Re-pointing the fixture would mean re-running the read-back and re-writing the
numbers; the phase chain and the weighting would not change.

One honest weakness: `SUBJ-015`'s end-of-study measurement came out at 47.3,
which is low for a control-arm completer (that arm's completers average 60.94).
That is a genuine draw from the seeded stream and it is reported as such; it
makes the decoy slightly *harder*, because the subject also looks like a poor
responder. Their attendance record is unambiguous, so the claim is still fair.

## Cross-task overlap

`cohort_enrolment`, `cohort_visit_log` and `cohort_outcome` are new tables
created only by this task's `extra.sql`. They do not collide with the eight baked
tables, nor with `gl_period_close` from `journal-balance-forensics`, nor with the
`flag-precedence-conflict` task authored alongside this one — that task creates
no tables at all and this one creates no files under `/data`. The tool allowlist
overlaps with other sqlite tasks in the suite, which is intended; the allowlist is
not a differentiator.

## Not verified

- **No container was booted.** `environment/Dockerfile` was not built. The `COPY`
  and `RUN` lines and the five build-time assertions are reasoned from the
  template's documented injection routes, not from a successful `docker build`.
  Every assertion's predicate was executed against a scratch database built from
  the same `extra.sql` and passes — 180 / 720 / 133 rows, 134 end-of-study
  attendances, 11 tables — but `sqlite3` being present in the base image is
  assumed, not tested.
- **`extra.sql` was never executed against the real `/data/db/turing.db`.** The
  baked-table safety test used eight stand-in tables named after the baked eight
  in a scratch database. It demonstrates that the SQL adds three tables and
  mutates nothing pre-existing; it does not demonstrate anything about the real
  file's contents, and the `IF NOT EXISTS` clauses would silently no-op if a
  table of the same name already existed there.
- **The task was not run.** No agent and no oracle execution happened, so "the
  oracle scores 1.0" is an argued property, not a measured one: every claim in
  `tests/reward.toml` was checked by hand against `solution/solve.sh` and against
  `fixtures/GROUND_TRUTH.md`, and each of the 14 has a corresponding passage in
  the oracle answer.
- **The judge was not invoked.** No OpenRouter call was made; claim wording has
  not been exercised against `openrouter/anthropic/claude-sonnet-5`.
- **The difficulty target is design intent, not measurement.** No Kimi-K3 or
  GLM5.3 rollout was performed. The claim that those models land a partial pass
  rests on the weighting arithmetic above and on the argument for each weighted
  claim, not on observed coverage.
- **`target_tool_calls = 56` is an estimate**, not a measured trajectory length.
- **The carried-forward method is the one the prompt specifies, not the only
  defensible one.** Last-observation-carried-forward is stated in
  `instruction.md` ("carried in at the last measurement we have for them") so the
  claimed numbers are derivable; a real analysis would likely prefer multiple
  imputation or a mixed model, which would give different values. The claims are
  fair against the prompt, not against best statistical practice.
- **The MCP tool behaviours asserted in the distractor rationale are not
  re-tested here.** That `sqlite_read_records` is equality-only and that
  `cli-mcp-server_run_command` forbids pipes are taken from the suite's existing
  conventions documents, not from a live call in this environment.
