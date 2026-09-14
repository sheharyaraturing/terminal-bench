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

## Build four tables before you judge any claim

The read above gives you the map. It does not survive contact with a long rubric: these
files run to forty, fifty and sixty claims, and the defects that ship are not the ones
that look wrong in isolation — they are the ones that only appear when claims are put
BESIDE each other, or beside the fixture. Unaided reading, one claim at a time, is how a
claim demanding a superlative the prompt never asked for, or a claim missing the waiver
its twin carries, gets waved through by a reviewer who could recite the rule against it.

So build these four tables once, before any claim criterion gets a verdict, and reuse them
across the criteria that need them. All four are mechanical, and all four come from files
the task ships — none of them needs a run.

1. **The claim ledger** — one row per claim, every claim, no exceptions. Columns: the value
   or outcome it grades; the phrase in `instruction.md` that cues it (blank if none); the
   relief or scope language it carries (blank if none); whether its referents resolve
   backwards; whether its premises were checked; the source its value comes from; its
   derived rewardkit id. A criterion is judged by reading DOWN a column, which is what makes
   a missing cue or a missing waiver visible. An empty cell is a candidate finding, and a
   claim absent from the ledger has not been reviewed.
2. **The alias table** — for every referent a claim requires to be identified (entity, site,
   person, party, column, file, document, category), every handle the ENVIRONMENT gives it:
   name, id or code, position or index, filename, own heading, role. Built from the fixtures,
   not from the prompt. This is the table `graded_names_accept_every_alias_the_environment_uses`
   is judged against, and it is where the largest family of false-FAILs is caught.
3. **The relief diff** — every widening clause in `tests/reward.toml` ("counts in full",
   "references are acceptable", "do not withhold for", "is graded separately", "a complete
   enumeration is not required"), with the list of claims carrying each. Reading it as a diff
   is the cheapest audit in this document: where one claim carries a clause and a claim
   grading the same kind of fact does not, that asymmetry IS the finding, and the author's own
   sentence is the fix.
4. **The grounding map** — for every rule, term and unit a claim grades, the file and sentence
   in the agent-visible set that establishes it, or "not found". A row reading "not found" is a
   claim grading a definition the agent never sees.

Two of these are exact computations rather than judgements, so run them rather than
estimating: the rewardkit id column (first 40 characters of the description, lower-cased,
every run of non-alphanumeric characters replaced by one underscore, trimmed — then group and
count collisions), and any count, window or tally a claim asserts (recompute it from the
fixture, including a shipped repository or bundle at each ref it exposes).

## Judge each criterion as its own critical block — re-read its files

The read above builds your map of the task; it does not settle any criterion. Treat
EVERY criterion as a self-contained critical block: before you write its verdict, go
BACK to the specific file(s) that criterion governs and re-read the relevant part with
that criterion's question in mind. Do not judge a criterion from memory of an earlier
pass or from a general impression of the task — the defect a criterion exists to catch
is usually in a detail you skimmed the first time, and each criterion asks a DIFFERENT
question of the same files. The task is judged one criterion at a time; a criterion is
never waved through on the strength of having read the file once for something else.

For each criterion, in turn:

- **Reach the files it actually bears on, and open them again.** As a guide to what to re-open:
  - `instruction_*` → `instruction.md` (plus `task.toml` `[metadata]` for persona/domain);
  - `environment_*`, `dockerfile_*`, `distractors_*` → `environment/Dockerfile`, `environment/fixtures/**`, any setup SQL;
  - `mcp_*`, `tool_surface_*` → `task.toml` `[[environment.mcp_servers]]` and `[metadata].enabled_tools`;
  - `solution_*`, `numeric_claims_*` → `solution/solve.sh`, re-read against the fixtures it draws from;
  - `claims_*`, `rubric_*`, `reward_*`, `judge_*` → `tests/reward.toml`, claim by claim, and the oracle it must agree with;
  - `verifier_*`, `cross_file_*`, `task_is_runnable_*` → `tests/test.sh`, `task.toml`, and every file they reference.
- **Re-read the criterion's own guidance** (in the rubric) and this document's rule for it,
  then read the file against THAT question — not the question the previous criterion asked.
- **Hold the block to the two-sided gate and the witness rule.** A finding needs the
  quoted line from the file you just re-opened, its effect on ORACLE >= 0.95 or NOP <= 0.05,
  and a concrete witness. "I recall the Dockerfile looked fine" is not a review — re-open it
  and confirm against the criterion in front of you.
- **Only after re-reading its files, and naming every instance, does the block get its
  verdict.** A criterion judged without re-opening the file it governs is an unrun check:
  return `not_applicable` and say the read was not performed, rather than passing it on memory.

## How to write the finding — plain language, ONLY what is wrong

The reason you write is read by a human who has to FIX the task fast. Write it so a
non-expert understands the problem in one read. Follow these rules for every criterion:

- **Say only what is WRONG.** Do NOT narrate what is correct. Cut lines like "the persona
  matches", "the judge is pinned", "the claims are atomic", "everything else checks out".
  A `fail` is a list of defects and nothing else. Never write the "this is right, this is
  right, HOWEVER this is wrong" pattern — cut straight to the wrong part.
- **A `pass` is ONE short line.** Normally "No issues found." Where the criterion told you to
  name what you checked — a recomputed figure, a fixture row, a simulated id set — put that in
  the SAME single line and stop: "No issues found; recomputed week 7 revenue from the fixture,
  13,688 matches". That one clause is what separates a check that was run from one that was
  waved through, so it stays; a paragraph touring everything that was correct does not.
- **Every `fail` names a concrete defect** — quote the offending text, or name the claim,
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
- **Short bullets, complete list.** The brevity rules above govern each BULLET, not how many
  there are. Six defects under one criterion means six bullets; the enumeration rule below is
  not relaxed by any of this. "Say only what is wrong" removes the praise, never an issue.
- **No fix essays.** A short "what it breaks" is enough, plus at most a short clause on what
  would make it right. The criteria below often describe the repair so you can recognise the
  defect — that is for your reading, not for the write-up: never turn it into a remediation
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
miss as real as never having looked.

A single task artifact can also trip SEVERAL criteria at once — but only when it carries
SEVERAL DIFFERENT DEFECTS. One reward claim that names two credit bars AND grades a value the
prompt never asked for is two findings: `claim_description_is_self_consistent` owns the first,
`claims_are_defensible` the second, and they have different witnesses and different repairs.
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

> **Same artifact + same witness + same fix = ONE defect.** If the answer that would be wrongly
> scored is the same answer, and the edit that repairs it is the same edit, it is one finding
> however many criteria the wording touches.

When the test says duplicate, file it once — under the criterion whose REPAIR it is — and in the
other criterion write a single cross-reference line ("the c15 absence-phrasing hole is filed
under `claims_assert_outcomes_not_topics`; no separate finding here") and judge that criterion on
whatever else it sees. A cross-reference is not a missed issue: the defect is on the record, with
the fix, exactly once.

The recurring duplicate pairs in this rubric, and who owns each:

- nothing grades the SET, so a fabricated extra is free → `claims_cover_the_whole_deliverable`
  (not also `rubric_penalises_padded_answers`);
- a claim earned by restating the prompt or quoting one fixture line →
  `claims_assert_outcomes_not_topics`, or `environment_does_not_leak_the_answer` when the value is
  in the tree (not also `rubric_is_not_trivially_satisfiable`);
- a claim missing the latitude its sibling carries → `claims_are_defensible` or
  `graded_names_accept_every_alias_the_environment_uses` where the dock is demonstrable; only
  `sibling_claims_carry_the_same_tolerances` when the sibling evidence is what makes the case;
- a bundled claim whose second half is undecidable from the answer text →
  `claims_are_decidable_by_reading` (not also `claims_are_atomic_and_specific`);
- two claims where one restates the other → `claims_do_not_subsume_or_contradict` (not also
  `claims_are_atomic_and_specific`).

A verdict is still per criterion: a criterion whose only issue is a duplicate PASSES if nothing
else trips it, and says which finding covers the artifact.

So within a single criterion's verdict, if more than one distinct issue is present, list ALL
of them — most critical first — each with separate evidence. Do not merge two defects into
one line, do not drop the quieter defect because a louder one shares the criterion, and do
not let a FAIL you have already reached end the search through the rest of the task. The pass
bar folds several smaller defects into one FAIL verdict; the EXPLANATION behind that verdict
must still enumerate every one, because each is a separate thing the author has to fix, and a
critical defect left off the list because a lesser one was already named is the failure this
gate exists to prevent.

## The pass bar

FAIL when the criterion is materially violated: one defect that makes the task
unrunnable, unsolvable, trivially satisfiable, or wrong; or several smaller defects
together. PASS when it holds — a single cosmetic nit does not fail a criterion, but
name it, in one line, as the whole of that pass's reason. Never pass leaving a real
defect unmentioned; never fail without naming one. Mark `not_applicable` only where
the criterion's own guidance allows it.

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
  convention this task does not follow. Drop or downgrade whatever does not survive.
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

