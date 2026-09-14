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

## What an explanation must contain

Every `fail` names a concrete defect: quote the offending text, or name the claim /
fixture / config key. Say what it does to the gate (which agent wrongly scores 1,
which correct agent wrongly scores 0, or which run crashes), and give the fix.
Every `pass` on a criterion where you checked something non-obvious should say what
you verified — "recomputed week 7 revenue from the fixture, 13,688 matches" is worth
more than "looks fine".

## Enumerate every instance — a criterion is a lens, not one slot

A criterion is a lens you pass over the WHOLE task, not a single slot that holds one
finding. When you apply it, report EVERY artifact that trips it — every claim, fixture,
comment or config line — each with its own quoted evidence and its own gate reasoning. A
31-claim rubric with four defensibility defects has four findings under
`claims_are_defensible`, not one; stopping at the first offending claim and moving on is a
miss as real as never having looked.

A single task artifact can also trip SEVERAL criteria at once, and each owns its own finding.
One reward claim that names two credit bars AND grades a value the prompt never asked for is
a finding under `claim_description_is_self_consistent` AND under `claims_are_defensible`;
`instruction.md` naming a tool AND leaking an expected number is a finding under
`instruction_no_scaffolding` AND under `environment_does_not_leak_the_answer`. Record it under
each — never let a finding on one criterion stand in for the finding another criterion owns,
and never decide "I already flagged that claim once" and drop the second angle.

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
say it. Never pass leaving a real defect unmentioned; never fail without naming one.
Mark `not_applicable` only where the criterion's own guidance allows it.

## Evidence, and how to avoid false findings

- **A finding needs a command and its real output.** "The verifier env block is missing"
  is an opinion; the parsed value showing it absent is a finding. A bar reported as met
  without its measured number is not a finding either.
- **Never present an unrun check as passed.** If a check cannot be run here — no upload
  archive, no run artifacts, no image, no credential — return `not_applicable` and say
  which input was missing. Oracle and nop verification are the usual casualties.
- **Read the current file before reporting.** A defect already fixed is stale; say so
  rather than reporting it.
- **Say when a suspicion fails to reproduce.** That is a useful result, not a blank.
- **Then argue against your own findings.** For each, check whether the information
  exists somewhere you did not look — another claim, the rubric header, a fixture comment, the
  Dockerfile, the prompt's own framing. Ask whether it is a real defect or merely a
  convention this task does not follow. Drop or downgrade whatever does not survive.
- **Greps over-flag.** Tool-name searches hit ordinary English: `time`, `memory` and
  `git` are words. Read the sentence before reporting a leak. An automated atomicity
  pass over-flags worse: almost every claim contains "and" and several numbers, and that
  is not the test — the test is whether the parts serve different goals.
- **Derive ground truth the same way every time.** Read the pre-fixture state from the
  pristine seed database (byte-identical to what the image serves); do not rebuild it
  from the CSVs. Apply the task's fixtures to a COPY, in the order the Dockerfile applies
  them. Never mutate the seed.
- **There is no model pass bar.** Do not fail a task because a model scored low. Grade
  the task. And a claim that every model misses identically is a claim defect, not a
  model result.

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

[
task/
  data of task

extra_refrence


]


Check.txt - harbor prompt -> 
