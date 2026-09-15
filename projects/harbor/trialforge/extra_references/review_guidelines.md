# TrialForge Task-Implementation Review — Guidelines

This is the shared review methodology for the TrialForge task-implementation rubric
(MCP Atlas / TrialForge tasks, Harbor schema 1.4). It applies to **every** criterion
in `tests/reward.toml`'s companion rubric: how to review, the gate each criterion
protects, the evidence a finding needs, what counts as "required", and the witness
rule for reporting.

Read this before you judge anything, and hold every criterion against it. The rubric
file itself now carries only the criteria; this document carries the method they all
depend on.

---

## What a task is

A  MCP tool-use task. An agent reads `instruction.md`, works inside a
sandbox built from `environment/Dockerfile` using the MCP servers declared in
`task.toml`, and leaves a final answer at `/logs/agent/final_answer.txt`. An LLM
judge (rewardkit) scores that text claim-by-claim against `tests/reward.toml`.

`tasks/<name>/` — **this is the complete, closed list. Nothing else may exist here.**

```
task.toml                 config: name, metadata, timeouts, MCP servers, verifier env
instruction.md            the prompt — the ONLY thing the agent sees
environment/Dockerfile    the sandbox: seed image + fixtures + setup SQL
environment/fixtures/     files copied into /data
solution/solve.sh         the ORACLE: the reference final answer
tests/reward.toml         the rubric: one [[criterion]] per ground-truth claim
tests/test.sh             verifier entrypoint: bridge output, run rewardkit
```

Any additional material a task needs lives under `environment/` (normally
`environment/fixtures/`) and nowhere else. There is no design-notes file: a `NOTES.md`
in the task folder is a defect, not documentation — see `task_folder_holds_only_task_files`.

## What is not part of the task

- **The reference folder.** The review pipeline copies its own `extra_reference/` folder (on
  some setups `extra_references/`) into the task copy you are given: this document, the tool
  list, the model catalogue, the environment docs. It is reviewer material the task author never
  shipped. Never flag it under any criterion, and never count it as a file in the task folder.
- **Anything outside the task copy.** The git branch the task lives on (a `.gitattributes`, the
  commit history), the built image, run artifacts and sibling tasks are not in front of you. A
  check that needs one of them is not_applicable for that part — say which input was missing —
  and is never a fail.

## Ground truth for the format

`mcpAtlasProject/TASK_FORMAT.md` explains the format, the Harbor pitfalls, and the
rewardkit contract, and walks both reference tasks. READ IT FIRST. It is the
authority on what each file is for. Where TASK_FORMAT.md and a task disagree about
what a field means, TASK_FORMAT.md wins; where it disagrees about a task's own
numbers, the task's files win (the doc can go stale — it already reports claim
counts that no longer match).

`tasks/TEMPLATE/` is the canonical skeleton: its comments state the rules
(persona voice, no tool names, likert/points=3, `judge` not `model`, `--with mcp<2`,
no `docker_image`). A task that violates a TEMPLATE comment is violating a rule
someone already paid for in debugging time.

## The organizing principle — the two-sided gate

Every criterion exists to protect one of two facts:

- **ORACLE >= 0.95** — the task is solvable and the verifier accepts a correct answer.
- **NOP <= 0.05** — the rubric is not satisfiable without doing the work.

When judging any criterion, ask which side of that gate a defect breaks. A claim the
oracle cannot satisfy breaks the first. A claim a blank answer earns breaks the
second. Say which one in your explanation.

## What is in scope right now

`solution/solve.sh` is reviewed as a FINAL ANSWER, not as a trajectory. There is no
trajectory grading in this pipeline yet: the judge is handed
`/logs/agent/final_answer.txt` and nothing else. So judge solve.sh on whether its
TEXT is the right answer, complete, grounded in the real environment, and in the
persona's register — not on how it was produced (both reference tasks legitimately
`cat` a pre-derived answer). Trajectory criteria — tool-call efficiency, phase
ordering, whether the agent actually used the servers — are deliberately DEFERRED and
will be added when trajectories are captured. Do not fail a task for lacking them,
and do not reward `[judge].atif_trajectory` usage yet.

## Method — miss nothing

1. Read `instruction.md` and write down the CHECKLIST of deliverables it asks for,
   including precision demands ("every figure to the dollar") and the qualitative
   asks ("why", "flag it", "which would you publish"). As you read, mark any
   AMBIGUITY a claim could ride on — a counted quantity with no defined unit, a
   phrase with two competent readings, an ask that only directs method — because a
   claim built on it false-FAILs many rollouts at once (see `instruction_is_unambiguous`).
2. Read `tests/reward.toml` and list every claim.
3. Read `solution/solve.sh` and list every assertion it makes.
4. Then reconcile the three lists IN BOTH DIRECTIONS. Deliverable with no claim,
   claim with no deliverable, claim the oracle does not satisfy, oracle statement
   nothing checks — each is a separate finding.
5. Read `environment/Dockerfile` + `fixtures/` and confirm every input those three
   documents assume actually exists at the path they assume, and that the numbers
   are derivable from it. Spot-check arithmetic you can compute from the fixtures.
6. Read `task.toml` and `tests/test.sh` as the wiring: could this task even run.

Steps 2–4 are written down, not held in your head: the claim × check matrix below is where
every claim meets the prompt, the oracle and the fixtures.

## Build the claim × check matrix before you judge any claim

The read above gives you the map. It does not survive contact with a long rubric: these
files run to forty, fifty and sixty claims, and the defects that ship are not the ones
that look wrong in isolation — they are the ones that only appear when claims are put
BESIDE each other, or beside the fixture. A review that judges claims by reading them finds a
different subset of those defects each time it runs, which is why a second review of an
unchanged task keeps finding issues the first one missed. The matrix closes that gap: every
claim meets every check once, in writing, before any claim criterion gets a verdict. Keep it
in your scratch file, outside the task folder. None of it needs a run.

**1. Extract the mechanical facts with one script.** Write and run a single script that reads
`tests/reward.toml` and the task's text files, and prints:

- every claim, numbered c1..cN in file order, with its full description;
- its rewardkit id — the first 40 characters of the description, lower-cased, every run of
  non-alphanumeric characters replaced by one underscore, trimmed — and every group of claims
  that share one;
- every relief or waiver clause ("counts in full", "is acceptable", "do not withhold",
  "graded separately", "is not required", "wording is free") with the claims carrying each;
- every identifier a claim names (a record id, code, name, SHA, date or figure) with all the
  claims naming it — these are the groups for the pair checks;
- for every figure, date and identifier in a claim, each place it appears in
  `instruction.md`, `solution/solve.sh` and the text files under `environment/`;
- a skeleton row per claim carrying every column key below, with ID and GROUP filled in;
- **phrase flags** — every claim containing wording behind the defects that most often slip
  between reviews:
  - a bar the judge cannot check from the answer alone: "from the tree", "of the tree", "true of
    the", "any route", "supported by the", "the data shows" → rule on it in JUDGE;
  - a widening that can set a second full-credit bar: "so does", "either one of", or "counts in
    full" followed by "provided" → rule in TEXT on whether it creates a second bar;
  - an accepted handle introduced by "or the …" or "(or the …)" → rule in ALIAS on whether that
    handle also fits something else in the tree.

Do not rebuild any of this by reading, and do not skip it because the rubric is short. Every
flagged claim gets an explicit ruling in the named column — `!` with the finding, or `ok` with
the reason the phrase is harmless — never a bare `ok`.

**2. List the referents once.** For everything the claims require to be identified — an
entity, site, person, party, column, file, document, category — write every handle the
ENVIRONMENT gives it: name, id or code, position or index, filename, own heading, role, and
the other end of any two-ended fact ("our house holds no permission" / "the rights sit with
the agency"). Build it from the fixtures, not the prompt; the ALIAS column reads it. Also list
every handle a claim uses that fits MORE than one thing in the tree ("the scope note" where a
withdrawn version of the note also ships) — a claim accepting that handle pays an answer resting
on the wrong one.

**3. Fill one row per claim — every column, no blanks.** Take the claims one at a time, with
the claim, the prompt, the oracle and the fixture its value comes from open together. A cell
is `ok` (checked, clear), `n/a` with a three-word reason, or `!` with a pointer — a quoted
phrase or file:line — to what you found. CUE, SRC and ORACLE always carry a pointer, because
several criteria read them. A blank cell is a check that was not run. Write rows in batches,
not one edit per cell.

- **CUE** — the `instruction.md` phrase that asks for this claim's value, verdict or precision,
  or NONE. → `instruction_states_the_deliverable`
- **READ** — a second competent reading of that phrase that changes the graded answer: another
  counting unit, another instant, method rather than output, a scope read closed.
  → `instruction_is_unambiguous`
- **SRC** — the file, table or row the graded value comes from.
  → `environment_provides_required_inputs`, `reward_is_graded_in_practice`
- **ORACLE** — the `solve.sh` line that satisfies the claim in substance, or NONE, or DIFFERS.
  → `solution_satisfies_every_claim`, `claims_are_traceable_to_the_solution`
- **PREM** — each fact the claim's own sentence asserts (a count, window, author, record state,
  mechanism), checked against the fixture; recompute any figure the claim compares, ranks,
  counts, or reaches by more than one route.
  → `claim_premises_are_true_of_the_environment`, `numeric_claims_survive_the_data_traps`
- **TERMS** — the deciding rule, each term and each unit the claim grades, with the file:line
  that states it, or NOT FOUND. → `claims_are_grounded_in_stated_evidence`
- **ALIAS** — whether the claim accepts every handle its referents have in step 2, and whether a
  handle it accepts also fits something else in the tree.
  → `graded_names_accept_every_alias_the_environment_uses`
- **RELIEF** — in both directions: relief a claim grading the same kind of fact carries and this
  one lacks (a waiver, an accepted handle), AND a restriction or scope qualifier a sibling carries
  and this one lacks ("at the time the batches were made" on one claim but not its twin) —
  the second kind pays a wrong answer, so its witness is the answer that scores without it.
  → `sibling_claims_carry_the_same_tolerances`
- **PIN** — the `claims_are_defensible` labels that apply: ENUM, UNCLOSED_SET, FRAGILE,
  ESTIMATOR, FRAMING, TRAJECTORY, MISALIGNED, CONTRADICTS. → `claims_are_defensible`
- **OUTCOME** — names the topic only, grades an absence a blank answer earns, restates the
  prompt, or grades a bare count or an agreement without its value or members.
  → `claims_assert_outcomes_not_topics`, `rubric_is_not_trivially_satisfiable`
- **TEXT** — two full-credit bars, a waiver that names nothing, a referent with no antecedent,
  an exclusion a judge could read as an inclusion. → `claim_description_is_self_consistent`
- **JUDGE** — a bundle whose parts move a score; arithmetic, re-derivation, or material the
  judge is not given; a bar a strict and a lenient judge would split; a grade on something other
  than the answer. → `claims_are_atomic_and_specific`, `claims_are_decidable_by_reading`,
  `judge_is_pinned_and_the_verdict_is_stable`, `rubric_provenance_without_leaking_answers`
- **TOL** — exact or stochastic; whether the tolerance admits a value printed elsewhere in the
  task, or excludes the oracle's. → `claims_are_stable_with_justified_tolerances`
- **LEAK** — whether one shipped file hands over the value without the work (check the known
  false positives first). → `environment_does_not_leak_the_answer`
- **ID**, **GROUP** — from the script. → `rewardkit_contract_is_correct`,
  `claims_do_not_subsume_or_contradict`

A filled row reads like this:

```
c15 | CUE "why the mean came out low" | READ ok | SRC fixtures/registry.sql:7 | ORACLE solve.sh:41 | PREM ok | TERMS ok | ALIAS ! names "Kirkmantle" only; the registry row also gives site 04 | RELIEF ok | PIN ok | OUTCOME ok | TEXT ok | JUDGE ok | TOL n/a exact value | LEAK ok | ID states_that_kirkmantle_submitted_height | GROUP Kirkmantle
```

**4. Write the set-level lists under the matrix.**

- **Deliverables** — each thing `instruction.md` asks for, with the claims that grade it or
  NONE; the scope parameter that decides which records are in play, and the claim whose
  correctness turns on it; the claim that fails a false positive, or NONE.
  → `claims_cover_the_whole_deliverable`, `rubric_penalises_padded_answers`
- **Set members** — for every set `instruction.md` asks for ("every record that is exposed", "which
  extracts clear", "everything to do before release"), derive EVERY member from the fixtures
  yourself, one per line, with the claim that grades it (or NONE) and whether `solve.sh` names it
  (or MISSING). Do not start from the claims or the oracle — start from the tree. A NONE is a
  coverage finding; a MISSING is a `solution_answers_the_instruction` finding.
  → `claims_cover_the_whole_deliverable`, `solution_answers_the_instruction`
- **Oracle extras** — each load-bearing statement in `solve.sh` that no claim grades.
  → `claims_are_traceable_to_the_solution`
- **Pairs** — inside each identifier group, every pair tested in BOTH directions: can an answer
  earn A and fail B, and can one earn B and fail A. A "no" in either direction means one claim
  implies the other. Add any claim the task's correct answer must deny.
  → `claims_do_not_subsume_or_contradict`
- **Traps** — EVERY distractor or trap the environment ships, including the ones that label
  themselves, with the single axis that rules it out and the claims an answer that falls for it
  would lose — or NONE. A label in the tree makes a trap resolvable; it does not make falling for
  it cost anything. NONE is a finding (known false positive 12 says when it is not).
  → `distractors_are_deliberate_and_fair`
- **Sources** — how many claims rest on each source: each fixture, the database, each server
  surface. → `reward_is_graded_in_practice`

**Three of these lists go into the verdict itself, pass or fail.** A list that only lives in the
scratch file is easy to skip, so these criteria print theirs as the last line of their reason,
compactly:

- `claims_cover_the_whole_deliverable` — "Set members:" every member of each set the prompt asks
  for, each with the file:line that puts it in the set, then its claim or NONE, and MISSING where
  `solve.sh` leaves it out (`A (build file:9) → c7; B (lockfile:4) → NONE, MISSING`). Build each
  set from EVERY file that can add a member — every install step, every list, every table —
  not from the claims or the oracle. If every member you listed happens to have a claim, you have
  probably started from the claims: re-derive it from the files before you accept it.
- `distractors_are_deliberate_and_fair` — "Traps:" every distractor, each with the specific wrong
  statement an answer that falls for it would make, and the claim whose OWN wording fails that
  statement, with the failing clause quoted — or NONE. A claim on the same topic that an answer
  falling for the trap would still satisfy does not count; that entry is NONE.
- `sibling_claims_carry_the_same_tolerances` — "Qualifiers:" in two parts. "Relief:" each waiver one claim carries
  that a claim grading the same kind of fact lacks. "Restrictions:" group the claims that share an
  opening shape (the same verb and kind of object — every "lists X as work to be done …", every
  "states that the image installs …") and, inside each group, every qualifier some members carry
  and others lack: before/after, only, at the time of, for the target version. Write "none found"
  for an empty part. A missing restriction is reportable even where wording is not what the judge
  matches, because it pays a wrong answer.

A NONE or MISSING on the first list, a NONE on the second, or any entry on the third is a
candidate finding and goes through the pass bar like any other.

**Then judge each claim criterion by reading DOWN its column.** Every `!` is a candidate
finding for that criterion; put it through the pass bar below before filing it. The column is
also where asymmetries show — a waiver on one claim and not its twin, a site named by code in
one claim and by name in the next. A criterion whose column is all `ok` and `n/a` passes, and
its pass line says how many rows were read ("No issues found; 34/34 rows checked").

## Judge each criterion as its own critical block

The matrix is your map of the claims; it does not settle any criterion. Treat EVERY
criterion as a self-contained block, judged against its own question — never from memory of
an earlier pass or from a general impression of the task. Each criterion asks a DIFFERENT
question of the same files, and the defect it exists to catch is usually in a detail skimmed
the first time.

**Spend the time where defects hide.** Judge every criterion NOT named in the quick pass below
first — the claims, the solution, the prompt-against-claims and the leak and distractor criteria,
which read the matrix. Then take the configuration and wiring criteria
(`instruction_is_persona_prompt`, `instruction_no_scaffolding`, `instruction_not_ai_generated`,
`metadata_matches_the_task`, `target_claims_matches_criterion_count`, `task_is_long_horizon`,
`difficulty_is_essential`, `task_is_distinct_in_the_suite`, `scripts_and_configs_actually_run`,
`dockerfile_wires_fixtures_correctly`, `environment_mutations_are_verified`,
`environment_is_deterministic`, `mcp_servers_are_declared`, `mcp_server_hygiene`,
`tool_surface_is_a_deliberate_allowlist`, `solution_script_hygiene`,
`no_weights_and_the_pass_bar_is_honest`, `rewardkit_contract_is_correct`,
`verifier_bridges_agent_output`, `verifier_writes_reward_only_on_a_real_verdict`,
`task_security_and_secrets`, `task_folder_holds_only_task_files`, `task_is_runnable_as_configured`,
`answer_key_is_out_of_agent_reach`) in one quick pass: read the file each governs once, apply its
FAIL list, and write the one-line pass. They are checked with the same bar, just not at length.

For each criterion, in turn:

- **Re-read the criterion's own guidance** (in the rubric) and this document's rule for it,
  then read the evidence against THAT question — not the question the previous criterion asked.
- **Where it has a matrix column, read down the column.** The rows were filled with the claim,
  the prompt, the oracle and the fixture open, so the column is the re-read; re-open a file
  only to confirm the quote of a finding you are about to file.
- **For everything the matrix does not cover, open the files it bears on again:**
  - `instruction_*` → `instruction.md` (plus `task.toml` `[metadata]` for persona/domain);
  - `environment_*`, `dockerfile_*`, `distractors_*` → `environment/Dockerfile`, `environment/fixtures/**`, any setup SQL;
  - `mcp_*`, `tool_surface_*` → `task.toml` `[[environment.mcp_servers]]` and `[metadata].enabled_tools`;
  - `solution_*`, `numeric_claims_*` → `solution/solve.sh`, against the fixtures it draws from;
  - `verifier_*`, `cross_file_*`, `task_is_runnable_*` → `tests/test.sh`, `task.toml`, and every file they reference.
- **Hold the block to the two-sided gate and the pass bar.** A finding fails the criterion only
  when it is blocking (see "The pass bar"). "I recall the Dockerfile looked fine" is not a
  review — re-open it and confirm against the criterion in front of you.
- **A criterion judged without its column read or its files re-opened is an unrun check:**
  return `not_applicable` and say which read was not performed, rather than passing it on memory.

## How to write the finding — plain language, ONLY what is wrong

The reason you write is read by a human who has to FIX the task fast. Write it so a
non-expert understands the problem in one read. Follow these rules for every criterion:

- **Say only what is WRONG.** Do NOT narrate what is correct. Cut lines like "the persona
  matches", "the judge is pinned", "the claims are atomic", "everything else checks out".
  A `fail` is a list of defects and nothing else. Never write the "this is right, this is
  right, HOWEVER this is wrong" pattern — cut straight to the wrong part.
- **A `pass` is ONE short line.** Normally "No issues found." Where the criterion told you to
  name what you checked, add ONE short clause to the same line — "No issues found; recomputed
  week 7 revenue from the fixture, 13,688 matches" — not a list of everything that was correct.
  Non-blocking findings, if there are any, follow under "Non-blocking:"; nothing else follows —
  except the "Set members:", "Traps:" and "Qualifiers:" lines the matrix section requires.
- **A `fail` lists its blocking findings first, then "Non-blocking:" if there are any.** Every
  blocking finding names a concrete defect — quote the offending text, or name the claim,
  fixture or config key — and says what it does to the gate: which correct answer wrongly
  scores 0, which wrong answer wrongly scores 1, or which run crashes.
- **Explain it like I'm five (ELI5).** Plain, everyday words and short sentences. Say what is
  broken and what it causes, in terms anyone could follow. Avoid jargon; where a technical term
  is unavoidable, add a few plain words saying what it means. A reviewer skimming twenty
  findings should grasp each one instantly.
- **Always name the file, and the claim or line if you have it.** Start each issue with it:
  "`tests/reward.toml` c12 — ...", "`environment/fixtures/scope.md` — ...". A finding with no
  file name is not actionable.
- **One issue per bullet**, most important first. Keep each to a sentence or two: what is wrong
  -> where it is -> what it breaks. Quote the offending text briefly when it helps locate it.
  Where several claims carry the same defect with the same repair (c7, c9 and c11 all lack the
  waiver c2 carries), that is ONE bullet naming every one of them — never only the first.
- **Short bullets, complete list.** The brevity rules above govern each BULLET, not how many
  there are. Six defects under one criterion means six bullets; the enumeration rule below is
  not relaxed by any of this. "Say only what is wrong" removes the praise, never an issue.
- **No fix essays.** A short "what it breaks" is enough, plus at most a short clause on what
  would make it right. Where the obvious repair would trip another criterion — splitting a
  bundle so one half becomes copyable, adding a waiver that does not name what it excuses,
  adding a claim for a value the prompt never asks for — that clause names the safe repair
  instead, so the fix does not become next round's finding. Never turn it into a remediation
  plan or a to-do list for the author.

Example of the WANTED style (a FAIL):
> - `tests/reward.toml` c12 — asks for the "median" rebuild time, but `instruction.md` only asks
>   how long it has come to take, so an agent reporting the mean (a different but equally fair
>   average) is marked wrong for the word it chose.
> - `environment/fixtures/scope.md` — never says what "field exposure" means, and c24 grades that
>   exact judgement, so two correct-looking answers can argue it either way and only one scores.

Example of what to AVOID:
> The persona is consistent and the domain is right. The claims are atomic and the judge is
> pinned to a current model. HOWEVER, c12 asks for the median while the prompt never mentions it...

(Cut everything before "HOWEVER" — only the problem remains.)

## Enumerate every instance — a criterion is a lens, not one slot

A criterion is a lens you pass over the WHOLE task, not a single slot that holds one
finding. When you apply it, report EVERY artifact that trips it — every claim, fixture,
comment or config line — each with its own quoted evidence and its own gate reasoning. A
31-claim rubric with four defensibility defects has four findings under
`claims_are_defensible`, not one; stopping at the first offending claim and moving on is a
miss as real as never having looked. The same defect with the same repair on several claims is
the exception: it is one finding that names every claim it sits on, and leaving a claim off
that list is the same miss.

A single task artifact can also trip SEVERAL criteria at once — but only when it carries
SEVERAL DIFFERENT DEFECTS. One reward claim that names two credit bars AND grades a value the
prompt never asked for is two findings: `claim_description_is_self_consistent` owns the first,
`instruction_states_the_deliverable` the second, and they have different witnesses and different
repairs.
`instruction.md` naming a tool AND leaking an expected number is likewise two. Record each —
never let a finding on one criterion stand in for the finding another criterion owns, and never
decide "I already flagged that claim once" and drop a genuinely different angle.

## One defect, one finding — the duplicate test

The opposite error is just as damaging, and in practice it is the commoner one: the SAME defect
written out again under a second criterion's name. Reviews routinely fail four or five criteria
on one underlying problem — nothing scores the set, so an invented extra is free — and the
author then reads five blockers, edits five places, and creates new defects doing it.

Before you write a finding, apply this test against everything you have already filed this
round:

> **Same artifact + same repair = ONE finding.** If the edit that repairs it is the same edit,
> it is one finding however many criteria the wording touches. Where that one defect has more
> than one consequence — a dangling phrase that both pays a wrong answer and docks a right
> one — name each consequence inside the one finding.

**Where a finding is filed is fixed by the table below, not chosen per review.** File it under
its owner; in every other criterion it touches, write a single cross-reference line ("the c15
absence-phrasing hole is filed under `claims_assert_outcomes_not_topics`; no separate finding
here") and judge that criterion on whatever else it sees. A cross-reference is not a missed
issue: the defect is on the record, with the fix, exactly once. This table overrides any
sentence in a criterion's guidance that says to record the same finding in a second place
("record it in both", "report it there too", "flag it under that one too"). A defect the table
does not list goes to the criterion whose repair it is.

| The defect | Owner |
|---|---|
| A claim grades a value, statistic, intermediate figure, extra field, verdict or precision that `instruction.md` never mentions | `instruction_states_the_deliverable` |
| `instruction.md` mentions it, but only as method ("use the date in the scope note"), or in a phrase with two answer-changing readings (no counting unit, no instant, a scope the claim reads closed) | `instruction_is_unambiguous` |
| A claim accepts one handle, or one end of a two-ended fact, where the environment gives others | `graded_names_accept_every_alias_the_environment_uses` |
| A claim lacks relief that a claim grading the same kind of fact carries, and the relief is not about a handle | `sibling_claims_carry_the_same_tolerances` |
| Any other claim that fails a correct answer: an open value or format pinned, a set closed that the environment leaves open, a route or process graded, the prompt contradicted | `claims_are_defensible` |
| A rule, term or unit a claim grades is stated in no file the agent can read | `claims_are_grounded_in_stated_evidence` |
| A claim's own sentence asserts something false about the environment, or a mechanism that covers only part of the cases | `claim_premises_are_true_of_the_environment` |
| The oracle's text does not satisfy a claim — says nothing on it, or only implies it | `solution_satisfies_every_claim` |
| A claim and the oracle state the same quantity differently, or the claim's tolerance excludes the oracle's figure | `claims_are_traceable_to_the_solution` |
| A deliverable the prompt asks for has no claim, or nothing grades the set, so a fabricated extra costs nothing | `claims_cover_the_whole_deliverable` |
| A claim earned by a blank answer (an absence), by restating `instruction.md`, by naming the topic, or by a bare count or agreement without its value | `claims_assert_outcomes_not_topics` |
| A graded value that one shipped file hands over without the work, after checking the known false positives | `environment_does_not_leak_the_answer` |
| Author prose or a comment in a shipped file states an answer, the defect list, the route, or benchmark vocabulary | `no_answer_key_in_shipped_files` |
| The `reward.toml` header or comments state the answer or narrate the claims; a claim grades the setup rather than the answer | `rubric_provenance_without_leaking_answers` |
| A description with two full-credit bars, a waiver that names nothing, a referent with no antecedent, or an exclusion readable as an inclusion | `claim_description_is_self_consistent` |
| A bundled claim whose parts move a score | `claims_are_atomic_and_specific` |
| A claim the judge must compute, re-derive, or check against material it is not given — including a bundle whose second half the answer text cannot decide, and an open target ("any route the data supports") whose accepted answers can only be checked against the environment, even where it also reads as two bars | `claims_are_decidable_by_reading` |
| One claim implies, restates or contradicts another, or asserts what the task's correct answer must deny | `claims_do_not_subsume_or_contradict` |
| A tolerance that admits a wrong or handed-over value, or a stochastic value with no measured tolerance | `claims_are_stable_with_justified_tolerances` |
| Two claims share a rewardkit id | `rewardkit_contract_is_correct` |
| The same fact stated differently in two task files where no claim is involved — a header count, a setup comment | `cross_file_consistency` |
| `docker_image` set over an active Dockerfile, or a fixture no `COPY` uses | `dockerfile_wires_fixtures_correctly` |
| An `enabled_tools` entry whose server is not declared | `mcp_servers_are_declared` |
| A `uvx` server without `--with mcp<2`, or an unpinned server | `mcp_server_hygiene` |
| An extra file in the task folder | `task_folder_holds_only_task_files` |
| The agent can read `tests/` or `solution/`, or write the reward | `answer_key_is_out_of_agent_reach` |
| The answer never reaches the file the judge reads | `verifier_bridges_agent_output` |

A verdict is still per criterion: a criterion whose only issue is a duplicate PASSES if nothing
else trips it, and says which finding covers the artifact.

So within a single criterion's verdict, if more than one distinct issue is present, list ALL
of them — blocking first, most critical first — each with separate evidence. Do not merge two
defects into one line, do not drop the quieter defect because a louder one shares the
criterion, and do not let a FAIL you have already reached end the search through the rest of
the task: each defect is a separate thing the author has to fix, and one left off the list
because another was already named is the failure this gate exists to prevent.

## The pass bar — only a blocking finding fails a criterion

A single failed criterion stops the task, so a criterion FAILS only on a BLOCKING finding. The
decision is mechanical, not a judgement of how serious the finding feels.

**A finding is blocking when all four of these hold:**

1. **Quoted from the file as it is now.** You re-opened the file and the text is there — not
   recalled from an earlier read, and not what files of this kind usually say.
2. **It has a witness.** You can write out the correct answer a claim scores 0 or 0.5 (a
   false-FAIL witness), the wrong or skipping answer a claim pays (a false-PASS witness), or the
   build, run or grading step that breaks. For `claims_are_decidable_by_reading` and
   `claim_description_is_self_consistent` the witness is either two answers the claim's own
   wording would score differently, or a claim whose bar needs material the judge never sees
   ("true of the tree", "established from the tree", "any route the tree supports"). Where a
   criterion's guidance makes a rule an outright FAIL (a `CHANGE-ME`, a hardcoded credential,
   `docker_image` set over an active Dockerfile), quoting that rule is the witness.
3. **Not excused.** No "Do NOT flag" line in the criterion's guidance and no entry under
   "Known false positives" below covers it.
4. **The claim itself does not already hold.** Check the claim's OWN relief, a second reading of
   the claim's OWN wording under which every correct answer still scores, and the rule stated in
   another fixture. If one of those clears it, it is not a defect. Another claim catching the same
   error elsewhere does NOT clear it — each claim is judged alone, so a defect in this claim stays
   a defect in this claim.

**If a finding has a witness and passes 1, 3 and 4, it is blocking — whatever its size.** None of
these is a reason to make it non-blocking:

- "the cue is indirect rather than absent", or "the prompt sort of implies it";
- "it only costs one point" / "a correct answer still lands at 50 of 51";
- "the clause widens more than it narrows", or "the rest of the claim is still decidable";
- "another claim catches it on substance";
- "a judge would probably read it the right way";
- "it is a small wording fix".

**Non-blocking is a closed list** — a finding is non-blocking only when:

- no claim's score is involved at all — a sentence in `solve.sh` no claim grades, a comment, a
  stale count in a header, formatting; or
- the criterion's own guidance calls that exact thing worth a note but not a fail.

Before you write a "Non-blocking:" bullet, re-read it. If it names an answer that loses a point,
collects a claim, or costs nothing where it should cost something, it is blocking: move it up and
fail the criterion. A non-blocking bullet never fails a criterion, however many there are.

A finding that fails check 1, 3 or 4 is not a defect: drop it, with at most one clause saying the
suspicion did not reproduce.

Mark `not_applicable` only where the criterion's own guidance allows it, or where the thing to
judge lies outside the task copy (see "What is not part of the task").

## Evidence, and how to avoid false findings

- **A finding needs a command and its real output.** "The verifier env block is missing"
  is an opinion; the parsed value showing it absent is a finding. A bar reported as met
  without its measured number is not a finding either.
- **Never present an unrun check as passed.** If a check cannot be run here — no upload
  archive, no run artifacts, no image, no credential — return `not_applicable` and say
  which input was missing. Oracle and nop verification are the usual casualties.
- **Quote the file.** Every finding must carry a phrase copied out of the task in front of you.
  The files you were given are the whole of the evidence, so a finding that cannot be traced to
  text in them is not a finding. What this prevents is a review written from the SHAPE of the
  task rather than its contents: describing a scope note as carrying a field it does not carry,
  a fixture as saying what fixtures of this kind usually say, a claim as worded the way such
  claims usually are. Open the file, find the text, quote it — "the file probably also
  contains…" is never a finding.
- **Say when a suspicion fails to reproduce** — in one clause, so the next reviewer does
  not re-file it. Not a paragraph, and not an excuse to narrate what was correct.
- **Then argue against your own findings.** For each, check whether the information
  exists somewhere you did not look — another claim, the rubric header, a fixture comment, the
  Dockerfile, the prompt's own framing. Ask whether it is a real defect or merely a
  convention this task does not follow. Drop whatever does not survive; a finding that survives
  with a witness stays blocking.
- **A missing claim is a defect only where the prompt asks for the thing.** Where the value is
  not requested — the prompt directs what to compute AGAINST rather than what to print, or
  another claim merely depends on it being right — the gap is in `instruction.md` and belongs
  there. A criterion written to close it would be a misaligned claim on its face.
- **A loose claim is a defect only where the tighter version holds up.** Write the tightened
  wording out before you report the loose one: a bundle split in two, where one half is then
  copyable from the prompt; a description tightened to a literal filename the fixtures do not
  use; an open target closed with an enumeration plus an escape clause that admits a wrong
  answer. Where the tighter version carries a defect of its own, the claim as written is not
  the finding.
- **Say what closing a gap would cost.** A gap a FIXTURE could close (state the rule, delete the
  leaking sentence), or the PROMPT could close (ask for the thing), is cheap. A gap only a new
  criterion could close is dearer: every criterion added widens the distance between what the
  prompt asks and what the rubric grades, and that distance is what half the criteria here
  measure.
- **Greps over-flag.** Tool-name searches hit ordinary English: `time`, `memory` and
  `git` are words. Read the sentence before reporting a leak. An automated atomicity
  pass over-flags worse: almost every claim contains "and" and several numbers, and that
  is not the test — the test is whether the parts serve different goals.
- **Derive ground truth the same way every time.** Read the pre-fixture state from the
  pristine seed database (byte-identical to what the image serves); do not rebuild it
  from the CSVs. Apply the task's fixtures to a COPY, in the order the Dockerfile applies
  them. Never mutate the seed.
- **There is no model pass bar.** Do not fail a task because a model scored low. Grade
  the task.
- **Everything in this rubric is decidable from the task files.** Every criterion here is
  answerable from `instruction.md`, `task.toml`, `tests/`, `solution/` and `environment/`
  alone — tasks are reviewed before any run exists, so a criterion that needed run data would
  be an unrunnable check, and none remains. So never defer a finding to a run, and never write
  that scores would settle a question: if a claim looks unearnable, the evidence is in the
  file — the rule it grades is absent from the fixtures, its premise is false against the
  data, it pins one of several handles the environment uses, or its twin carries a waiver it
  lacks. Name the file and read it. Where run artifacts happen to be provided they are
  corroboration only; the finding must stand without them.

## Known false positives — check every finding against these before filing

Reviewers have filed each of these, and validation against the task files rejected them.
A finding that matches one is not a defect unless its "it IS a finding" condition holds. Each
entry covers only the pattern it names: it never excuses a finding outside that pattern, and a
finding outside every pattern is decided by the pass bar alone.

1. **"The graded value is printed in a fixture, so the claim is free."** The prompt names no
   files, so finding the right file among the distractors is the work. It IS a finding when the
   value needs no file at all — it is in `instruction.md` or is general knowledge (score that as
   the bluffer in `rubric_is_not_trivially_satisfiable`) — or when one mechanical pass over a
   summary file (a line count, a flag count) reproduces a value the task exists to derive.
2. **"The document under audit prints the figures, so they leak."** A report, card or close
   pack the agent is asked to check must show its own figures, and a withdrawn draft stating a
   wrong conclusion is the trap. It IS a finding only when a file states a value a claim grades
   AND no claim requires re-deriving, re-attributing or overturning it.
3. **"The scope note prescribes the method, so it hands over the route."** A client's method
   requirement ("compute it a second way on rank order") is the specification. A route leak
   spells out the steps to the finding ("compare row by row, then check week 30").
4. **"Part of the claim is copied, so the claim is free."** List what the claim requires beyond
   the copied value — the members, a comparison, an attribution, a derivation. If any of that is
   not handed over, the claim is not free.
5. **"The oracle words it differently from the claim."** Hold the oracle to the equivalence the
   rubric gives an agent: "never actually paid out … zero dollars behind it" satisfies "voided
   before payment released … no money moved". It IS a finding only when the oracle says
   something different, or nothing.
6. **"Earning A forces B."** Write the answer that earns A and fails B before filing; if it can
   be written, the implication is false. Test both directions — a pair is independent only when
   both such answers exist.
7. **"These sibling claims grade different quantities" or "this claim lacks its twin's relief."**
   Read the prompt's own word for the quantity first: two claims grading the one quantity it
   defines ("each cohort's contribution") are consistent even where one member's figures happen
   to coincide. Relief transfers only between claims grading the same kind of thing — count to
   count, value to value, explanation to explanation.
8. **"A fixture value has two readings."** Apply the claim under both readings of the DATA (a
   blank field read as "living" or as "unknown"). If every correct answer satisfies the claim
   either way ("the supplied records do not establish…"), it is not a finding. This covers the
   data only — a claim description whose own wording sets two bars is a
   `claim_description_is_self_consistent` finding, not this.
9. **"The claim is strict about layout or wording."** Read the relief the claim already carries
   and the prompt's own ask first. A claim that already accepts references, or grades a grouping
   the prompt asked for, is not strict.
10. **"The waiver accepts a word the environment never uses."** Accepting an extra word ("weak or
    negligible") widens the bar; it cannot fail a correct answer.
11. **"The claim adds a basis or provenance bar."** Where the task's finding IS the basis (288
    distinct incidents, not 300 stacked rows), requiring it is the point. It is a
    `MISALIGNED_CLAIM` only when nothing in the task turns on it.
12. **"The trap's rejection is not scored."** A trap is scored when any claim grades the correct
    disposition of the item it misleads about. It IS a finding only when no claim catches an
    answer that falls for it.
13. **"The direction changes no number."** A date, pin or territory that no row straddles still
    discriminates when the environment offers a rival value — the system clock, a card's
    timestamp, a withdrawn version's date.
14. **"0.5 cannot say which half was missing, so the bundle must be split."** `points = 3`
    supplies the partial band by design; a bundle is a finding only in the score-moving shapes
    `claims_are_atomic_and_specific` lists.
15. **"Several claims are cheap to earn, so the rubric is trivially satisfiable."** Do the
    arithmetic against the 0.85 gate; below it, that criterion passes.
16. **"The claim order follows the oracle's order."** Under individual judging, order changes no
    score.

## Three lenses, then compare

Audit independently along three lines before reconciling:

1. **Ground truth and solvability** — recompute the numeric claims exposed to a data trap
   off the fixtured data (triage per `numeric_claims_survive_the_data_traps`; a claim that
   only restates a stored value needs no recompute).
2. **Instruction and rubric** — read `instruction.md`, `tests/reward.toml` and `solve.sh`
   as one artifact and ask whether they describe the same task.
3. **Shipping and run forensics** — what actually gets uploaded, and what the trials did.

Disagreement between the lenses is itself a finding; say so rather than averaging it away.

## What counts as "required" — apply this in every criterion

A value or condition is required by the task ONLY when `instruction.md` literally states
it, or uses an unambiguous synonym with no other equally-valid reading. None of the
following makes a value required, and a claim that hinges on one is a rubric defect
rather than a correct check:

- thematic or descriptive wording ("do it properly", "make it clean");
- the name or title of an entity (a file called `..._BACKUP.csv` does not by itself
  require the answer to use the word "backup");
- THE ORACLE'S CHOICE OF A VALUE. `solve.sh` is ONE valid completion, not the
  standard. Where the instruction is silent — a format, an ordering, a framing, which
  of two correct labels to use — the rubric must accept any completion the environment
  permits, even though the oracle picked one;
- your own inference about what was probably intended.

When the instruction is silent on a value, the claim must accept whatever a correct agent
could legitimately produce. Do not invent requirements.

## Standard of evidence — name the witness

Findings in the claims blocks are only reportable with a concrete witness answer:

- **False-PASS witness** (for a coverage or weakness finding): describe a specific
  answer that satisfies EVERY existing claim while skipping the outcome you say is
  ungraded. If you cannot describe one, the outcome is already covered — do not report it.
- **False-FAIL witness** (for a strictness finding): describe a specific correct answer
  a competent agent would plausibly write that this claim would score 0 or 0.5. If you
  cannot, the claim is defensible — do not report it.

And when you propose a fix, respect the floor: **loosening a claim so that it would also
pass an agent who skipped the work is not a fix — it trades a false FAIL for a false
PASS.** Loosen to the weakest form that still fails a skipping agent; where a value is
genuinely needed, use the one the oracle actually produced.

