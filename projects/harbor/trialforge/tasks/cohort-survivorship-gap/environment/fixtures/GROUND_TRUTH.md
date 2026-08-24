# GROUND_TRUTH.md — cohort-survivorship-gap

Every number below was read **back out of the built artefact** by the read-back
stage of `build_fixture.sh` (`bash build_fixture.sh` regenerates this file).
`extra.sql` was executed into a scratch SQLite database and every figure here
was then obtained with SQL against that database. Nothing comes from the
builder's in-memory state.

## Safety of the injection

- tables created: `cohort_enrolment`, `cohort_visit_log`, `cohort_outcome`
- forbidden statements found in `extra.sql`: **none**
- `extra.sql` size: **62,622 bytes**

The file only creates new tables and inserts into them, so the eight baked
tables in `turing.db` are untouched.

## Shape

- `cohort_enrolment` rows: **180** (one per enrolled subject)
- `cohort_visit_log` rows: **720** (**4** scheduled visits per subject: 1 `BASELINE`, 2 `WEEK_4`, 3 `WEEK_12`, 4 `END_OF_STUDY`)
- `cohort_outcome` rows: **133**
- subjects per arm: CONTROL **90**, INTERVENTION **90**
- subjects per site: SITE-01 45, SITE-02 45, SITE-03 45, SITE-04 45
- enrolment window: 2023-01-09 to 2023-06-25
- subjects in `cohort_outcome` that are not in `cohort_enrolment`: **0**

## Layer 1 — the outcome table covers completers, not enrolments

- subjects with an outcome row: **133** of **180** enrolled = **73.9%**
- subjects an inner join between enrolment and outcome silently drops: **47**
- retention read off the inner-joined set alone: **100.0%** — every row in that set has an outcome by
  construction, so the join makes the metric unfalsifiable rather than good

Per-arm outcome coverage:

| arm | enrolled | with an outcome row | coverage |
|---|---:|---:|---:|
| CONTROL | 90 | 77 | 85.6% |
| INTERVENTION | 90 | 56 | 62.2% |

## Completion as the visit log defines it

A subject completed if the visit log records `attended = 1` at the
`END_OF_STUDY` visit.

- completers: **134**
- dropouts (enrolled, did not attend the end-of-study visit): **46**
- true completion rate: **134/180 = 74.4%**

- subjects with all four visits attended: **128**. Counting completers
  that way misses **6** subjects who skipped one
  intermediate visit and still attended the end-of-study visit, and would give
  **71.1%** instead.
- dropouts whose last attended visit is later than their attended-visit count
  implies (intermittent attendance): **6**

| arm | enrolled | completers | dropouts | completion rate | dropout rate |
|---|---:|---:|---:|---:|---:|
| CONTROL | 90 | 78 | 12 | 86.7% | 13.3% |
| INTERVENTION | 90 | 56 | 34 | 62.2% | 37.8% |

## Layer 2 — the dropouts are not missing at random

- of the **46** dropouts, **34** are in INTERVENTION and **12** in CONTROL
- dropout rates: INTERVENTION **37.8%** against CONTROL **13.3%** — a differential of **24.4 percentage points** exactly (**24.5** if the two rates are rounded before subtracting)

Dropouts by site, to test the competing explanation:

| site | enrolled | dropouts | dropout rate |
|---|---:|---:|---:|
| SITE-01 | 45 | 12 | 26.7% |
| SITE-02 | 45 | 12 | 26.7% |
| SITE-03 | 45 | 11 | 24.4% |
| SITE-04 | 45 | 11 | 24.4% |

The site marginals are flat, so a site effect does not account for the
concentration. The arm marginals are not.

### Direction of the bias

- mean last-observed score of the **46** dropouts: **45.51**
- mean endpoint score of the **133** subjects with an outcome row: **62.53**
- the dropouts sit **17.02 points** below the
  analysed set, so dropping them biases every arm mean UPWARD, and biases the
  arm that lost more subjects upward by more

| arm | mean last-observed score of its dropouts |
|---|---:|
| CONTROL | 52.04 |
| INTERVENTION | 43.2 |

## The between-arm comparison flips

### As analysed — completers with an outcome row only (the inner join)

| arm | n | mean endpoint score |
|---|---:|---:|
| CONTROL | 77 | 60.94 |
| INTERVENTION | 56 | 64.72 |

INTERVENTION leads CONTROL by **3.78 points**.

### Every enrolled subject, last observation carried forward

Each subject contributes their endpoint score if they have one, otherwise the
interim score from their last attended visit. All 180 enrolled subjects
carry a value; 47 of them are carried forward.

| arm | n | mean carried-forward score |
|---|---:|---:|
| CONTROL | 90 | 59.6 |
| INTERVENTION | 90 | 56.59 |

CONTROL leads INTERVENTION by **3.01 points**.

- completers-only difference (INTERVENTION − CONTROL): **+3.78**
- carried-forward difference (INTERVENTION − CONTROL): **-3.01**
- **the sign flips**: YES
- total swing: **6.79 points**

## Decoy — a completer with no outcome row

completers with no row in `cohort_outcome`: **1**

- **`SUBJ-015`** — arm CONTROL, site SITE-01. Attended **4 of 4** scheduled
  visits including `END_OF_STUDY`, with an end-of-study interim score of
  **47.3**. There is no `cohort_outcome` row for this subject.
  This is a missing final assessment, not a withdrawal: the subject
  completed. Counting enrolled-minus-outcome as dropouts therefore reports
  **47** dropouts when the true figure is **46**,
  and a completion rate of **73.9%** rather than **74.4%**.

Consistency checks that make the decoy unambiguous:

- dropouts holding an outcome row: **0**
- enrolled subjects with no visit-log rows at all: **0**
- subjects carrying more than one outcome row: **0**
- visit-log rows with `attended = 0` carrying a non-null interim score: **0**

So the only inconsistency anywhere in the three tables is that one missing
outcome row.

## Numbers that appear in no claim

Individual subject scores, visit dates and enrolment dates are drawn from a
seeded stream and nothing about any single one of them is asserted, apart from
the decoy subject named above. Only the aggregates in this file are claimed.
