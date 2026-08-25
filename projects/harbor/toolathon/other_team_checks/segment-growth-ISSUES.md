# `segment-growth` — issues and fixes

Consolidated fix list as of 2026-08-24. Covers [PR #23](https://github.com/turing-rlgym/context-mesh/pull/23) (head `8c32180`) and everything still open from the [v3 review](segment-growth-v3.md). Baseline `origin/main` at `a5ad18b`.

Every item below was measured, not inferred. Companions: [PR review](segment-growth-PR23.md) · [v3 review](segment-growth-v3.md) · [QC report](../qc-reports/segment-growth-report.xlsx).

**Current state:** oracle 1.0 on all four dimensions, key exact (0 cell diffs of 246), 15 of 18 ablated rules load-bearing. Nothing here is a correctness bug — these are leakage, calibration and plumbing issues.

| Group | Count |
|---|---|
| Blocking on PR #23 | **2** |
| Should also fix in PR #23 | **3** |
| Open major, needs its own PR | **1** |
| Structural, needs a decision | **1** |
| Minor | **7** |
| Suite-level, not this task | **3** |

---

## A. Blocking on PR #23

### A1 — `artifacts` is in the wrong table, so it does nothing

**File** `tasks/generated/segment-growth/task.toml`

The PR puts `artifacts` *inside* `[task]`. TOML then parses it as `task.artifacts`, and nothing reads that key.

| | top-level `artifacts` | `task.artifacts` |
|---|---|---|
| `restatement-vintages` (known-working) | `['/app/vintage_report.xlsx', …]` | ABSENT |
| **PR 23** | **ABSENT** | `['/app/growth.xlsx']` |

Evidence: all 24 tasks that declare it use line 2, top level, before any table · `qa/qa_check.py:812` reads `t.config.get("artifacts", [])` and still reports `QC34 — declares no artifacts` on the patched tree · top-level placement is what actually caused collection to work on `restatement-vintages`.

**Fix** — move the line above `[task]`:

```toml
schema_version = "1.4"
artifacts = ["/app/growth.xlsx"]

[task]
name = "context-mesh/segment-growth"
```

*Verify:* `python3 -c "import tomllib;print(tomllib.load(open('task.toml','rb')).get('artifacts'))"` must print the list, not `None`.

### A2 — `a_reward` was removed, so the viewer's headline number becomes a binary gate

**File** `tasks/generated/segment-growth/tests/reward.toml`

The PR renames `a_reward` → `reward` instead of adding it. All 25 sibling tasks declare **both**. `qa/lens.py:39-41` explains why:

> *"`a_reward` duplicates `reward` under a name that sorts first, because Harbor's viewer renders its Result column from the alphabetically first metric key."*

| | Alphabetically first metric | Viewer Result column |
|---|---|---|
| Before PR | `a_reward` | correct |
| **After PR** | **`artifacts`** | **the binary shape gate** |
| Correct | `a_reward` | correct |

**Fix** — declare all three:

```toml
[[reward]]
name = "a_reward"
aggregation = "weighted_mean"

[[reward]]
name = "reward"
aggregation = "weighted_mean"

# Strict benchmark gate.
[[reward]]
name = "pass_gate"
aggregation = "threshold"
threshold = 1.0
```

Keep the `[[reward.criteria]]` block under whichever weighted entry you prefer. Note separately that those criteria weights appear to be **inert** — see `D1`.

---

## B. Should also fix in PR #23

### B1 — the new grader trips `QC15`, taking the checker from 7 HIGH to 8

**File** `tests/missing_values/check.py`

```
HIGH  QC15  #27 dimension 'missing_values' shows no fractional score - it looks binary.
```

False positive on substance — it returns an F1. But `qa_check.py:444` matches `/\s*(?:denominator|total|len\(|max\(|float\(|n_|count)`, and the new code divides by `precision_den` / `(precision + recall)`, which match nothing.

**Fix** — rename the two denominators so they match the `n_` alternative:

```python
n_predicted = true_positive + false_positive
n_expected  = true_positive + false_negative
precision = true_positive / n_predicted if n_predicted else 0.0
recall    = true_positive / n_expected  if n_expected  else 0.0
```

**Tested against the actual regex.** `precision_denominator` does **not** work — the token has to sit immediately after the slash, so `/ precision_denominator` misses. `/ max(precision_den, 1)` also passes and is behaviourally identical (when the denominator is 0 the numerator is 0 too), but the rename reads better.

### B2 — drop `args = []`

**File** `task.toml`. Neither the suite template nor any of the 25 other tasks declares it. Harmless, but it is unrequested drift from the template, and `QC36` already flags this task for machinery drift. Remove the line.

### B3 — rebase

The branch's merge-base is `4f24fff`; `main` is at `a5ad18b`, 3 commits ahead. Those three touch only `doa-routing`, so there is no conflict and the review holds — but rebase before merging.

---

## C. Open major — needs its own PR

### C1 — the `Note` column is a cheat sheet, 100% recoverable

**File** `environment/task/initial_workspace/restatements.csv` · **untouched by PR #23** · flagged on two consecutive revisions.

The `Note` column states the governing rule in plain English:

```
S002,2023,1650,2026-03-01,Approved,Future-dated; ignore
S005,2024,820,2026-01-20,Draft,Not approved
S024,2023,2445,2025-12-12,Approved,Latest applicable correction
S024,2023,2500,2026-02-20,Approved,After cutoff; ignore
S028,2024,3125,2025-07-01,Withdrawn,Withdrawn; ignore
S009,2022,0,2025-11-01,Approved,Zero is authoritative
S011,2025,,2026-01-15,Approved,Approved deletion / missing value
S035,2024,,2025-10-21,Approved,Restates value to missing
```

**Measured:** drop any row whose `Note` matches `ignore|not approved|withdrawn|draft`, then among survivors prefer one saying `latest|supersed`. That reproduces the rule-based answer on **13 of 13 SegmentID+Year keys — 100%**, without opening the methodology. It bypasses four separately-stated rules:

| Rule the Note gives away | Cells it protects |
|---|---|
| `Status` must be `Approved` | 4 |
| `PublishedAt <= as_of_date` | 6 |
| Latest `PublishedAt` wins | 4 |
| Blank approved Revenue means missing | 2 |

**Fix — two parts.**

**(a) Regenerate the notes from one shared grammar**, drawn independently of `Status`, `PublishedAt` and blankness. This is exactly the fix that worked on `restatement-vintages`, where an earlier draft leaked `basis` at 100% precision and the rebuilt column carries zero signal. Shape of it:

```python
ACTION = ["figures lodged with group", "return filed", "submission logged",
          "resubmitted", "revised return", "correction logged", "re-keyed",
          "amended submission", "figures updated", "entry posted"]
REASON = ["", "", "", " after review", " on reconciliation", " following query",
          " per group instruction", " after variance check", " on consolidation"]
TAIL   = ["", "", "", " (ref AP-{n})", " ref {n}", " [{ini}]", " ticket GRP-{n}"]
# draw one of each per row, seeded deterministically, with NO reference to
# Status, PublishedAt, or whether Revenue is blank.
```

**Acceptance test — commit it as a probe.** No keyword filter over `Note` may recover `Status`, the cutoff outcome, latest-wins, or blankness above chance. Concretely: the 13/13 figure must fall to what a random tie-break gives.

**(b) State it in the methodology.** Add one line to the `Restatements` section of the `Methodology` sheet, mirroring `restatement-vintages`:

> `Note` is the filer's own commentary, keyed free-hand. It carries no authority, is not a classification field, and nothing in this policy may be inferred from it.

**The answer key does not change** — only the text of a column nothing is allowed to read.

---

## D. Structural — needs a decision

### D1 — 0.50 of every score is free, which is what holds the floor at 0.72

Four equally-weighted dimensions, two of which (`artifacts`, `shape`) test only that the workbook is well-formed and carries the segment list — and that list is handed to the agent in `segment_master.csv`. Measured floor, through the PR's own graders:

| Submission | Before PR | After PR |
|---|---|---|
| Oracle / exact answer | 1.0000 | 1.0000 |
| Blank cells instead of `N/A` | 0.7821 | **0.8068** ↑ |
| Every cell written `N/A` | 0.7500 | **0.5816** ↓ |
| Rows in RawData order | 0.7500 | 0.7500 |
| **Follow the archive methodology in full** | **0.7189** | **0.7189** |
| Header row only / no file | 0.0000 | 0.0000 |

PR #23 closes the all-N/A exploit but **does not move the floor** — the binding case was always the archive-methodology follow, and that is untouched. This is `QC24 #36` from the repo's own checker.

Two notes on the direction of travel:

- **One wrong answer got cheaper.** F1 rewards precision, and a submission writing blanks instead of `N/A` has *perfect* precision with recall 5/39, so it rose to 0.8068 — despite the methodology explicitly requiring `N/A`. Defensible as a trade, but it should be deliberate.
- **I mis-scoped my own prediction.** I said the fix would take the floor to "about 0.25". The *dimension* fell to 0.326, close to that; the *mean* only reached 0.58, because I was scoring the exploit and ignoring the free 0.50.

**Fix — pick one:**

1. **Fold the shape gate in.** Make `artifacts` and `shape` preconditions rather than paid dimensions: if either fails, the whole reward is 0. Cleanest, and it makes `pass_gate` redundant.
2. **Split the substantive work across more dimensions** so the shape gate's share falls — e.g. separate `restatements`, `rule_precedence` and `rounding` out of `growth`. More work, better diagnosis.

Option 1 is one change to `reward.toml` plus a guard; option 2 is the better benchmark. **This is a design call, not a defect — it needs a decision before the next run, because it determines what a partial score means.**

---

## E. Minor

| ID | Issue | Fix |
|---|---|---|
| `E1` | **Inclusive cutoff is inert.** The methodology says `PublishedAt` is *"on or before"* `as_of_date`, but no restatement is dated `2026-02-15`, so an exclusive bound moves **0 cells**. Nearest are 02-14 (inside) and 02-20 (outside). | Move `S019 2024` from `2026-02-10` to `2026-02-15`. It already fills a raw gap, so the cell is already graded. One date, rerun the key. |
| `E2` | **`DisplayOrder` is decorative.** `segment_master.csv` is already stored in `DisplayOrder` order, so reading top-to-bottom gives the same result without consulting the column. | Shuffle the CSV row order so file order and `DisplayOrder` disagree. Key unchanged. |
| `E3` | **`shape` collapses five failures into one `0.0`** — row order, extra rows, missing rows, wrong names, wrong year columns are indistinguishable. A model with 39 of 40 segments reads the same as one that emitted the wrong file. | Split the year-column check from the row-order check. |
| `E4` | **Extra rows are free** in `growth` and `missing_values` — both iterate `want_order` and never consult invented segments. Only `shape` notices. The dead helper `produced_cells_count`, commented *"should count unexpected/missing cells as misses"*, shows the intent existed. | Finish that intent, or document it as deliberate. |
| `E5` | **Dead code.** `_non_empty_sheets` in `artifacts/check.py` and `produced_cells_count` in `growth/check.py` are defined and never called. | Delete both. |
| `E6` | **README lists twelve failure modes with no measurements.** | Publish the ablation table and the naive-probe floor from the [QC report](../qc-reports/segment-growth-report.xlsx). |
| `E7` | **No format-example artifact** (`QC13 #17`). The output shape is prose in `Methodology` rows 59–60. | Add a `Format_Example.xlsx` as `restatement-vintages` and `vendor-outliers` do. A shape stated as data cannot be misread as guidance. |

---

## F. Suite-level — not this task's PR

| ID | Issue | Fix |
|---|---|---|
| `F1` | **`pass_gate` is counted as a dimension.** `AGGREGATE_KEYS = {"reward","a_reward"}` at `qa/lens.py:61` and `qa/qa_check.py:968` is used to *exclude* aggregates when listing dimensions, so a 0/1 threshold gate pollutes every per-dimension statistic. Not fixed by PR #23. | Add `"pass_gate"` to `AGGREGATE_KEYS` in both files. |
| `F2` | **The template still checks out CRLF** (79 CR bytes in `tasks/template/environment/runtime/setup.sh`), which makes `QC36` fire falsely against every task that correctly pins LF. `segment-growth` is right and the template is stale. | Add the same `.gitattributes` at the repo root, or to `tasks/template/`. |
| `F3` | **`QC08` cannot see a spec held as a worksheet.** It reports `segment-growth` has no spec document because it only scans prose files — the actual spec is the 60-row `Methodology` sheet inside `segments.xlsx`, and the file it *does* find is the distractor. Same heuristic will misfire on any workbook-spec task. | Teach `QC08` to read `.xlsx` sheets, or let a task declare its spec location. |

---

## Recommended order

**Before merging PR #23:** `A1`, `A2` (blocking) · `B1`, `B2`, `B3` (cheap, same PR). Total maybe fifteen minutes, and no key regeneration.

**Before the next model run:** `D1` — decide how the shape gate is weighted. Without it, a 0.72 will be read as "most of the way there" when it means "produced a well-formed but wrong workbook."

**Then:** `C1`, the `Note` regeneration. Largest effort, largest remaining leak, and the key does not move.

**Whenever:** `E1`–`E7`, and raise `F1`–`F3` with whoever owns `qa/` and `tasks/template/`.

## Verification checklist

After each change, re-run:

```bash
cd "Z:/Turing/Projects/Tool Decathlon/context-mesh" && python3 qa/qa_check.py tasks/generated/segment-growth --min INFO
```

and confirm:

- oracle scores **1.0** on all four dimensions, key diff **0 of 246**
- no-op and header-only shell both **0.0**
- top-level `artifacts` parses to a list
- `reward.json` carries `a_reward`, `reward` **and** `pass_gate`
- `QC15` and `QC34` no longer fire
- the naive-probe floor has moved (it is 0.7189 today)
