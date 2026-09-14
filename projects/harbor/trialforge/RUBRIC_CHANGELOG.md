# TrialForge quality-gate update — 2026-09-11

Closes the gaps found by two independent QC passes over the task suite: the first reviewer's
report (`data/missing checks 2/pull-sept-9-2026-issues (2).md`, 16 findings) and the
independent QC workbook (`data/missing checks/MCP_Atlas_QC_Independent.xlsx`, 91 findings),
as adjudicated in `data/issues_that_are_valid.md`.

**Every check added here is decidable from `task/` alone — no `runs/` folder, no scores, no
trajectories.** Tasks are reviewed before any run exists, so a criterion that needed run data
would be an unrunnable check. The one criterion that did need one was removed.

## Files changed

| File | Before | After | Change |
|---|---|---|---|
| `rubrics/task-implementation.toml` | 51 criteria, 1100 lines | **54 criteria, 1230 lines** | 4 added, 1 removed, 17 sharpened |
| `extra_references/review_guidelines.md` | 251 lines | **326 lines** | 4 pre-judgement tables; write-up rules; static-only rule; scratch block removed |
| `new files/checks.txt` | 102 lines | **143 lines** | "How to write your review" wording rules (placeholders untouched) |

Not touched: `rubrics/compact/*` (both variants), `project.toml`, `checks/`, `tasks/`.

## Why the old rubric missed these

Sorting the 27 adjudicated-valid defects by *why* the rubric did not catch them:

| Root cause | Count | Fix |
|---|---|---|
| The lens existed but only looked at `instruction.md`, never at the fixtures or data | 11 | sharpened + new mechanical passes |
| No lens existed at all (sibling asymmetry, false premises, judge inversion, source coverage) | 10 | 4 new criteria |
| The lens was correct but prescribed prose reading over 47–64 claim rubrics | 4 | enumerative tables, mandated |
| The lens deferred to run artifacts the reviewer never has | 2 | hedges deleted |

The taxonomy was not the problem. The procedure that applied it was.

---

# 1. New criteria (4)

## `graded_names_accept_every_alias_the_environment_uses`

**Catches the largest defect family (6 of 27):** a claim pins one name for a thing the
environment names several ways, so an agent that reads the data and answers in the data's own
vocabulary is docked on vocabulary alone.

Adds an **alias table built from the fixtures** (not the prompt), covering the classes that
recur: name ↔ id/code; column ↔ position/index; file ↔ its own heading ↔ its document type;
party ↔ role; and converse framings of one fact. Hard rule: *an answer that quotes the
environment's own words for a thing can never fail a claim about that thing.* Where one claim
in the file already spells out two handles and its neighbours name one, the asymmetry settles
the question.

Why it is not folded into `claims_are_defensible`: that criterion's mechanical pass says
*search `instruction.md`* — and every one of these aliases lives in the fixtures. One
(`parts[5]` for a column named `channel`) is not a string anywhere; it is a position.

## `sibling_claims_carry_the_same_tolerances`

**Catches 4 defects, and it is the cheapest pass in the review.** Nothing else in the rubric
compares claims *to each other* — every other claims criterion reads one claim at a time.

Procedure: extract every relief clause in `reward.toml` ("counts in full", "references or
unambiguous titles are acceptable", "do not withhold for", "graded separately", "a complete
enumeration is not required"), say what each excuses, find every claim whose grading turns on
the same thing, and flag those that lack it. Runs in the **strictness direction** too: where
one direction of a comparison spells out a scope qualifier and its mirror does not, the
unqualified claim is scoped differently from the way it reads.

Guard against over-correction: a waiver must never excuse the load-bearing value, and a
waiver copied without naming what it excuses is the vacuous waiver
`claim_description_is_self_consistent` fails.

## `claims_are_grounded_in_stated_evidence`

**Catches 5 defects, including the most expensive single defect in the batch.**

For every claim, extract three things and grep the agent-visible set for each: the **deciding
rule** behind any judgement it grades, every **term** it treats as defined, every **unit or
basis** it pins. A term that appears only in `reward.toml` (which grades it) and
`instruction.md` (which merely *asks* about it) has zero grounding.

Named failure shapes: the rule is absent; the policy states the rule for a **neighbouring**
case and is silent on the graded one; the rule is **asymmetric and unstated** so every correct
agent answers symmetrically; a graded **term** is undefined (which also destroys grading
stability, since the judge has no rule either); a graded **unit** is unestablished; a graded
**method detail** is unrecorded. Explicitly: *a reporting directive is not a definition.*

## `claim_premises_are_true_of_the_environment`

**Catches 4 defects.** A claim description is not only a target — it is a set of assertions
about the world, and they reach the judge as fact. A false one docks the answer that states
the truth *and* rewards the answer that parrots the claim.

Two passes: **premise check** (recompute counts and windows; check a named author, source or
described document against the file that records it — including whether it records one at
all) and **literal-rule execution** (run the claim's own wording as a specification and
confirm it yields the claim's own value; if not, the claim depends on a restriction it never
states).

The expensive shape it names: an **incomplete mechanism**, where the claim's stated reason
covers a subset of the cases it claims to explain — so the agent that traces the behaviour
properly states the general rule and scores zero, while the agent that repeats the claim's
narrower story collects full credit.

---

# 2. Removed (1)

## `validation_gates_were_actually_run`

The only run-dependent criterion. At review time it could only ever return
`not_applicable`, which made it a parking space for findings that belong elsewhere. Removed;
the statically-checkable part moved into `cross_file_consistency` — a task documenting a
different bar, or recording a gate result its current claims cannot produce, is drift like any
other and is caught by re-reading the claims and the oracle.

---

# 3. Sharpened (17)

| Criterion | What was added |
|---|---|
| `claims_are_defensible` | New labels **`ESTIMATOR_PREFERENCE`** (pins a statistic/aggregation/basis the task never fixes — plus the test that if two legitimate estimators both land inside the claim's own tolerance, the claim grades vocabulary) and **`FRAMING_PREFERENCE`** (accepts one end of a two-ended fact). New `MISALIGNED_CLAIM` shapes **(iv)** intermediate figure the prompt never asked to see and **(v)** unrequested field bundled beside a requested value. `TRAJECTORY_PREFERENCE` extended with the **documented-route** case. Mechanical pass now runs against the fixtures, pointing at the alias criterion. |
| `claim_description_is_self_consistent` | **Exclusion read as inclusion** — resolve every referent backwards; a forward-dangling demonstrative in a disqualifier clause is a finding on its own, and the proven shape ("it fails only where…") is the fix. **Waiver waives a relationship without pinning the other side**. Waivers must be **imperative and element-naming**. Run-artifact fingerprints deleted, replaced by a static two-reading test. |
| `claims_do_not_subsume_or_contradict` | Grouping is now mechanical — **group by identifier token** (record ids, codes, entity names) and read each group straight through. New shape: **record state phrased as a disposition**, where one claim grades what the system says while a sibling requires the action denying it. Plus: a claim the task's own correct answer must deny is a finding even without a colliding sibling. |
| `environment_does_not_leak_the_answer` | A leak is a file that **yields** the value, not only one that states it: for every graded count, total or set, run the one-command test (line count, flag count, sort, single query). Shipped repositories and bundles must be checked **at every ref**. |
| `instruction_is_unambiguous` | **The evaluation instant is unfixed** — selectors with "still", "currently", "as of" or a present participle must say when they are judged; evaluate each at the review instant and at event time and see if the record set changes. Disambiguation elsewhere in the prompt does not repair a selector that inverts on its own. |
| `instruction_states_the_deliverable` | The claim→prompt reconciliation becomes an explicit **claim × cue ledger**, one row per claim with the cueing phrase quoted or the cell left empty. Names the three shapes that fill empty cells: unnamed statistic, intermediate figure, bundled extra field. |
| `claims_cover_the_whole_deliverable` | New gap shape: **scope parameter not graded** — the as-of date, cut-off, basis or population rule that decides which records are in play. |
| `rubric_penalises_padded_answers` | New defence: **a claim that fails a false positive**. At least one claim must be scored against the set, not its members, so a fabricated member costs points rather than merely failing to gain them. |
| `reward_is_graded_in_practice` | **Map claims onto sources and check every source is load-bearing.** A source or whole discovery layer that ≤1 claim needs is a phase that can be skipped wholesale. |
| `rewardkit_contract_is_correct` | The eyeball replaced by the **exact id rule**: first 40 characters of the description, lower-cased, every run of non-alphanumerics → one underscore, trimmed. Simulate for every claim, group, report each collision group and the count of ids lost. Fix is to make the **first 40 characters** distinct. |
| `claims_are_atomic_and_specific` | The process-claim ban extended to the **documented-route** case — grading the answer's account of *how* a documented fact was established. |
| `distractors_are_deliberate_and_fair` | **A trap must fail on exactly ONE dimension** (one that fails on three axes discriminates nothing) **and its rejection must be scored somewhere** — name the claims a trap-swallowing answer would fail, or the trap is decoration. Plus **inert discriminators**: a directed choice must have a record on the other side of its boundary. |
| `cross_file_consistency` | **What a claim says about a fixture** is drift too — authorship, document identity, record state, row counts. Plus the statically-checkable half of the removed gate criterion. |
| `environment_provides_required_inputs` | Cross-reference: inputs *existing* is this criterion; whether the environment states the **rule, term or unit** a claim grades belongs to `claims_are_grounded_in_stated_evidence`, and a pass here may not stand in for that. |
| `claims_assert_outcomes_not_topics` | The dangling-referent hole now points at its false-FAIL twin: one unresolved phrase can produce both a free pass and an inverted fail. |
| `numeric_claims_survive_the_data_traps` | Cross-reference: a claim that only restates a stored value can still carry a false premise in the sentence around it. |
| `no_weights_and_the_pass_bar_is_honest` | Run-artifact hedge removed — the file is the whole check and it is sufficient. |

---

# 4. `review_guidelines.md`

**Added — "Build four tables before you judge any claim."** The read of the task gives a map;
it does not survive a 64-claim rubric. All four are mechanical and come from shipped files:

1. **The claim ledger** — one row per claim: value graded · cueing phrase · relief language ·
   referents resolved · premises checked · source · derived rewardkit id. Criteria are judged
   by reading *down* a column. A claim absent from the ledger has not been reviewed.
2. **The alias table** — every handle the environment gives each referent.
3. **The relief diff** — every widening clause and the claims carrying it.
4. **The grounding map** — every graded rule, term and unit → the file and sentence that
   establishes it, or "not found".

**Replaced — "What an explanation must contain"** → **"How to write the finding — plain
language, ONLY what is wrong"** (see §5).

**Replaced — the orphan sentence** *"a claim that every model misses identically is a claim
defect, not a model result"* (true, but it had no criterion, no verdict line, and no run data
at review time) with the rule that **every criterion is decidable from the task files**, so a
finding is never deferred to a run.

**Removed** — a stray scratch block at the end of the file.

---

# 5. `new files/checks.txt` — how findings are written

Ported from the webdev project, which already defines this. Placeholders unchanged:
7× `{task_path}`, 1× `{file_tree}`, 1× `{criteria_guidance}`.

1. **Say ONLY what is WRONG.** No narrating what is correct; the "this is right, this is
   right, HOWEVER this is wrong" pattern is banned. A FAIL is a list of defects and nothing
   else.
2. **A PASS is one short line** — normally "No issues found."; where the criterion asked what
   was checked, that clause goes in the same line and stops there.
3. **ELI5** — plain words, short sentences, what is broken and what it causes.
4. **Always name the file and claim** — `tests/reward.toml c12 — …`.
5. **One issue per bullet, most important first** — what is wrong → where → what it breaks.
   **Brevity applies to each bullet, never to the number of bullets.**
6. **No fix essays** — at most a short clause on what would make it right.

Two consistency fixes this forced: the guidelines used to say a fail should *"give the fix"*
while checks.txt said *"do not suggest fixes"* (now aligned), and two lines that invited
narration (the cosmetic-nit allowance on a pass, and "say when a suspicion fails to
reproduce") are now capped at one clause.

---

# 6. Traceability — every valid finding to the criterion that now owns it

## Source 1 — first reviewer (16 findings: 13 valid, 3 invalid)

| # | Finding | Now owned by |
|---|---|---|
| 1 | quoted-delimiter c14 — stated reason covers 939 of 1,029 surviving rows | `claim_premises_are_true_of_the_environment` |
| 2 | quoted-delimiter c8 — asymmetric with c6 | **invalid** — no check added |
| 3 | translation-rights c6/c8 — one-sided framing | `claims_are_defensible` (`FRAMING_PREFERENCE`) |
| 4 | translation-rights c7/c9/c11 — missing the title waiver | `sibling_claims_carry_the_same_tolerances` |
| 5 | translation-rights c13 — "scores layout" | **invalid as framed** — no check added |
| 6 | translation-rights c14 — waiver names nothing | `claim_description_is_self_consistent` |
| 7 | translation-rights c19 — docks the fixture's own words | `graded_names_accept_every_alias_…` (party ↔ role) |
| 8 | translation-rights c10 — blank `died` field | **invalid** — no check added |
| 9 | accrual — a currency the agent cannot know | `claims_are_grounded_in_stated_evidence` (unit) |
| 10 | changeset c6+c15 — gated on 26, never requested | `claims_are_defensible` (intermediate figure) |
| 11 | changeset c6 — false premise about the window | `claim_premises_are_true_of_the_environment` |
| 12 | changeset c3/c15 — redundancy (no edit needed) | `claims_do_not_subsume_or_contradict` (existing) |
| 13 | batch-declared c5 — the present-tense participle | `instruction_is_unambiguous` |
| 14 | batch-declared c24 — undefined term | `claims_are_grounded_in_stated_evidence` (term) |
| 15 | batch-declared c18 — the waiver its sibling has | `sibling_claims_carry_the_same_tolerances` |
| 16 | batch-spec c2 — dangling referent, judge inverts | `claim_description_is_self_consistent` |

## Source 2 — independent QC (all 9 HIGH + all 14 MEDIUM, plus the trap family)

| # | Sev | Finding | Now owned by |
|---|---|---|---|
| 1 | HIGH | access-source c7 — gold unreachable from its own wording | `sibling_claims_carry_the_same_tolerances` + premises |
| 2 | HIGH | batch-declared c5 — "still running" at which instant | `instruction_is_unambiguous` |
| 3 | HIGH | batch-spec c2 — exclusion read as inclusion | `claim_description_is_self_consistent` |
| 4 | HIGH | cron c12 — median vs mean | `claims_are_defensible` (`ESTIMATOR_PREFERENCE`) |
| 5 | HIGH | derived-variable — site named one of three ways | `graded_names_accept_every_alias_…` |
| 6 | HIGH | provenance — unstated asymmetric resolution rule | `claims_are_grounded_in_stated_evidence` |
| 7 | HIGH | quoted-delimiter c22 — column name vs position | `graded_names_accept_every_alias_…` |
| 8 | HIGH | translation-rights c6/c8 — wording | `claims_are_defensible` (`FRAMING_PREFERENCE`) |
| 74 | HIGH | award-chain — policy never states the exposure rule | `claims_are_grounded_in_stated_evidence` |
| 10 | MED | accrual — undefined currency unit | `claims_are_grounded_in_stated_evidence` |
| 12 | MED | assay c2 — the cited file *is* the analysis plan | `graded_names_accept_every_alias_…` (file ↔ title) |
| 13 | MED | assumed-role c33 — claim contradicts its fixture | `claim_premises_are_true_of_the_environment` |
| 14 | MED | batch-declared c24 — ungrounded term | `claims_are_grounded_in_stated_evidence` |
| 16 | MED | changeset — `CHANGES.md` yields the answers by grep | `environment_does_not_leak_the_answer` |
| 21 | MED | coursepack c9/c10 — unasked publication years | `claims_are_defensible` (bundled field) |
| 22 | MED | coursepack c12 — unverifiable method detail | `claims_are_grounded_in_stated_evidence` |
| 24 | MED | derived-variable c7 — pays for one route only | `claims_are_defensible` (documented route) |
| 28 | MED | freeze-thaw c40 vs c42 | `claims_do_not_subsume_or_contradict` |
| 31 | MED | mirelune c39 — missing the siblings' waiver | `sibling_claims_carry_the_same_tolerances` |
| 32 | MED | translation-rights c7/c9/c11 — waiver asymmetry | `sibling_claims_carry_the_same_tolerances` |
| 75 | MED | award-chain — cut-off ungraded | `claims_cover_the_whole_deliverable` |
| 75 | MED | award-chain — no false-positive penalty | `rubric_penalises_padded_answers` |
| 77 | MED | award-chain — document layer carries 3.2% | `reward_is_graded_in_practice` |
| 87 | MED | case-pack c21 — enumerate-then-waive | `claim_description_is_self_consistent` |
| 51 | LOW\* | collective-licence — over-determined trap, rejection unscored | `distractors_are_deliberate_and_fair` |
| 52/53 | LOW\* | inert review date / inert term boundary | `distractors_are_deliberate_and_fair` |
| — | — | 23 × criterion-name collisions | `rewardkit_contract_is_correct` |

\* LOW in the workbook, confirmed valid and included.

---

# 7. Deliberately not covered

- **The 3 invalid findings** (first reviewer #2, #5, #8). Adding checks for them would
  manufacture false findings: #2's two claims ask for the same quantity ("contribution"), #5's
  claim already carries two tolerances, and #8's claim ("the supplied records do not
  establish") is satisfied under both readings of the blank field.
- **~28 LOW workbook findings** that are reward-shape judgement calls rather than checkable
  fact (#17, #18, #25, #27, #29, #33, #35–#37, #41, #48, #55, #58, #61, #70, #76, #78–#84,
  #88–#91). The LOW families kept are the name collisions and the trap/inert-discriminator
  family.
- **Workbook #73 (INFO)** — its own text reads *"nothing to fix in the files; it needs a
  run"*: reward-signal firing, rewardkit parsing, oracle attainability, nop floor, image
  build, servers starting. No check added.
- **Run-only evidence generally.** Judge-inconsistency statistics, per-claim earn rates and
  trajectory call counts were used to *rank* this work. None is an input to any check, and
  witnesses in the new guidance are written as hypothetical answers, never trial ids.

---

# 8. Verification performed

Each new check was executed against the real task folders using **only `task/`**:

| Check | Result |
|---|---|
| grounding (term) | `grep -ril "field exposure" …/environment/` → 1 hit in `reward.toml`, 1 in `instruction.md`, **0 in the environment** |
| grounding (unit) | **14** `$` values in `reward.toml`, **0** currency tokens across `instruction.md` + all fixtures; columns are bare `REAL` |
| grounding (rule) | award-chain §Exposure: all four sentences concern voided invoices; **0** files state a price-gap rule |
| premise (mechanism) | recomputed the fixture CSV: **939** lines split into nine parts, **1,029** rows keep the right amount |
| premise (false count) | `git rev-list --count` on the shipped bundle → **36** in the window; the claim says 34 |
| inversion | c2 *"has to rest on **that set of batches**"* vs siblings *"it fails only where…"* — one file |
| sibling diff | `"References or unambiguous titles are acceptable."` on c2/c4/c5/c12/c13, **absent** on c7/c9/c11 |
| alias | fixture row supplies three handles for one site; 8 claims name one, only one claim names two |
| trivial-count leak | `grep -cE '^- '` on `services/*/CHANGES.md` at HEAD → **entries 26, revised 8** = two claims' answers |
| scope parameter | cut-off present in the scope note, **0** occurrences in `reward.toml` |
| slug collisions | rule confirmed exact against `reward-details.json`; suite scan reproduces the reported worst cases (12 of 50 with a 4-way, 9 of 55 with a 6-way, 7 with a 7-way) |
| contradiction | grouping by one record id pulls 13 claims together; the colliding pair sits three lines apart |
| estimator | `grep -ci median instruction.md` → **0**; `reward.toml` → **1** |

Structural: TOML parses, 54 criteria, 54 unique names, every criterion has a description and a
PASS/FAIL line, all 8 defensibility labels render as bullets. Traceability asserted
programmatically: **35/35 valid findings map to present guidance, 0 missing.**

---

# 9. Outstanding

- **`project.toml` points at a file that does not exist.** `rubrics =
  "rubrics/task-implementation.compact.toml"`; the compact variants live under
  `rubrics/compact/`, and `core/registry.py` resolves the path relative to the project dir
  with no fallback. Until that line points at `rubrics/task-implementation.toml`, none of this
  reaches the reviewer.
- **The compact variants were intentionally left stale** and still carry the old 51 criteria.

---

# 10. Round 2 — false-positive and stability pass (2026-09-14)

Driven by `data/Checks_after_update/mirelune_AR_issues_validated.xlsx`: four automated-review
rounds over one task, 32 issues raised, **24 VALID / 8 NOT VALID**, plus the pasted award-chain
and translation-rights runs. No criteria added or removed — 54 stands. Ten guidance changes, all
aimed at two failures: findings that do not move a score, and defects that pass silently.

## 10.1 The eight invalid findings, and what now suppresses each

| Invalid finding | Why it was wrong | Rule added |
|---|---|---|
| v1 `sibling_claims` (c15/c29/c24) | Relief language lowers a bar; its absence does not raise one. Only demonstrable case was already filed under `claims_are_defensible`. | Reporting bar is now **a demonstrable dock**, restricted to claims whose EXPRESSION is open; plus an explicit no-double-billing clause. |
| v1 `rubric_penalises_padded_answers` | Same "nothing scores the set" defect as the coverage finding in the same round. | **"One finding, not two"** — cross-reference when the coverage gap already carries it. |
| v1 / v2 / v3 `claims_are_atomic_and_specific` (3 rounds) | "0.5 cannot say which half failed" is report legibility; `points = 3` supplies the partial band by design. Acting on it produced a prompt-copyable claim and turned one leaked sentence into three free claims. | Bundling is reportable only when it **moves a score** — free credit for a wrong part nothing else grades, a free half, opposite failure modes, or an all-required bundle that zeroes a partly-correct answer. Plus: **test the split product before proposing it.** |
| v2 `rubric_is_not_trivially_satisfiable` | Every bullet restated findings filed elsewhere in the same round. | Leaky claims are reported **under the criterion that owns them**, not here. |
| v3 `distractors_are_deliberate_and_fair` | Argued a scope-note direction "changes no answer" — inertness is not the fairness test — and described a fixture line deleted two revisions earlier. | The **inert-discriminator test is withdrawn**; a direction that agrees with the tree is a consistency cue. Stale half handled by the quote-the-current-file rule. |
| v3 `rubric_is_not_trivially_satisfiable` | Self-refuting: computed "about 0.20 … well under the bar" and returned FAIL. Also cited a 0.75 bar that does not exist. | **Verdict decided by arithmetic against the 0.85 gate**; below the gate is a PASS, stated with the number. Only a claim a blank answer earns fails regardless. |

## 10.2 The cascade — fixes that created the next round's defects

The workbook traces each round's repairs to the issues they caused. Four had a rubric cause:

- **Coverage demanded a claim for an uncued value** (the current pin), the author added it, and the
  next round attacked that claim under five criteria. → `claims_cover_the_whole_deliverable` may now
  **never demand a claim for something the prompt does not ask for**; that finding belongs to the
  instruction criteria, and the preferred repair is the one that does not grow the rubric.
- **An ambiguity finding pushed a literal filename**, and the alias criterion then failed the claim
  because the fixtures say "the image lockfile at the repo root". → `claims_are_defensible` now fixes
  ambiguity by **acceptance plus disqualification**, never by demanding a literal string.
- **An unbounded target was repaired with an enumeration plus an open escape clause**, recreating the
  two-bar defect and paying full marks to a check that provably would not work. → repairs must
  **close the target**.
- **Restatement across criteria** made one defect read as four or five blockers. → the duplicate test
  in the guidelines.

## 10.3 Misses — four on award-chain, three on translation-rights

Every missed defect was owned by a criterion that **passed silently**. Four verdicts now have to
carry their computation, so silence is visibly an unrun check:

| Criterion | Required in every verdict |
|---|---|
| `claims_are_grounded_in_stated_evidence` | the file + sentence establishing each graded rule/term/unit, or the empty search — starting from the judgement claims |
| `claims_cover_the_whole_deliverable` | what parameter decides which records are in play, and the claim that grades it, or "none does" |
| `rubric_penalises_padded_answers` | the claim that fails a false positive, or "none" |
| `reward_is_graded_in_practice` | the claims-per-source tally, one line per source |

Two sweeps were made exhaustive for the same reason: the alias criterion must **walk all five alias
classes and report each** (party ↔ role and converse framing are the ones that get skipped, and both
were missed on translation-rights), with a mechanical trigger for the converse-framing pair; and
`claim_description_is_self_consistent` must **list every waiver in the file before judging any**,
which is what catches a waiver that names nothing it excuses.

## 10.4 Guidelines and prompt

- **New section — "One defect, one finding — the duplicate test."** Same artifact + same witness +
  same fix = one finding, filed under the criterion whose repair it is, cross-referenced elsewhere.
  Lists the five recurring duplicate pairs and who owns each. The "one artifact can trip several
  criteria" rule is kept, narrowed to several DIFFERENT defects.
- **New section — "Your findings become the next revision."** Prefer fixture → prompt → existing
  claim over adding criteria; never demand a claim for an uncued value; check the repair you imply.
- **Stale findings** — every finding must quote text from the current file, or there is no finding.
- **`checks.txt`** mirrors the duplicate rule in both places that previously said "record it under
  each", and adds a seventh write-up rule: quote the file in front of you.

## 10.5 Verification

- 17/17 false-positive patterns (the 8 invalid findings plus the cascade causes) now have a
  suppressing rule; 7/7 misses now have a forced-evidence or exhaustive-sweep rule.
- 13/13 spot-checked true-positive rules survive the relaxation — including the two that sit closest
  to what was narrowed: the trap-discrimination and rejection-must-be-scored halves of the distractor
  criterion, and the three atomicity shapes the workbook upheld in v4.
- TOML parses; 54 criteria; placeholders in `checks.txt` unchanged (7 / 1 / 1).

## 10.6 Known trade-off

The **inert-discriminator** test is withdrawn, so the two LOW findings it was written for
(`composite-endpoint-recount-v10` #52, `coursepack-edition-clearance-v3` #53 — a directed choice with
no record on the other side of the boundary) will no longer be flagged as distractor defects. They
were LOW; the same test produced three rounds of invalid findings on one task and was rejected by the
validator on its own terms. Where such a claim actually pays for the directed choice, the copied-value
shape in `claims_assert_outcomes_not_topics` still catches it.

## 10.7 Regression after the relaxations — 93/93

| Set | Checked | Result |
|---|---|---|
| Round-1 valid issues (both original reviewers) | 38 rules | **38/38 still present** |
| Mirelune VALID issues across v1–v4 | 26 rules | **26/26 still present** |
| Mirelune NOT VALID (the 8 FPs) + cascade causes | 15 rules | **15/15 suppressing rule present** |
| Award-chain / translation-rights live run | 14 rules | **14/14** (valid still fire, misses forced, FPs suppressed) |

One tension surfaced by this regression and fixed: the scope-parameter shape in
`claims_cover_the_whole_deliverable` previously recommended "grade the parameter itself (one claim
naming the date)", which is the method-echo repair the mirelune workbook rules invalid. The repair is
now ordered — first a claim whose CORRECTNESS TURNS ON the parameter (a closed-set or false-positive
claim an answer built on the wrong cut-off cannot satisfy), and only where the prompt asks for the
parameter to be stated, a claim naming it. Award-chain #75a still fires; the mirelune c14 mistake is
not reproducible from this text.

