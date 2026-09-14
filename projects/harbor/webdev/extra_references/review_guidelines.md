# WebDev Task-Implementation Review — Guidelines

This is the shared review methodology for the WebDev task-implementation rubric
(codearena browser-judged app-build tasks, Harbor schema 1.4). It applies to
**every** criterion in `rubrics/task-implementation.toml`: how to review, the gate
each criterion protects, the two environments, the evidence a finding needs, what
counts as "required", the witness rule, and the enumerate-every-instance rule.

Read this in full BEFORE you judge any criterion, and hold every criterion against
it. Harbor strips the rubric file's own comments before you ever see it, so the
methodology those comments used to carry now lives here — it is not optional
background, it is how each verdict is meant to be reached. (This is reference
material for you, not task content you grade.)

---

## What a WebDev task is

A web-application BUILD task. The agent reads `instruction.md`, builds a running app
inside the container from `environment/Dockerfile`, and the app is graded FROM A REAL
BROWSER: a headless browser driven through Playwright MCP by an LLM judge (a pinned
model) opens the app's local URL, exercises the UI, and scores criteria. Grading is
spread across several DIMENSIONS, each a `tests/<dimension>/judge.toml` with its own
prompt, its own `[[criterion]]` list, and its own `[judge].weight`. There is no text
answer file and no deterministic grader here — the judge IS the verifier. The concrete
stack, port, launch command, and dimension NAMES are per-task choices; read THIS task's
files for its actual contract rather than assuming any of them.

**The judge's IDENTITY lives in `task.toml`, not in a `judge.toml`.** The driver, the
model id, and the reasoning effort are declared exactly once, in `task.toml`'s
`[verifier.env]` as `REWARDKIT_JUDGE` / `REWARDKIT_MODEL` /
`REWARDKIT_REASONING_EFFORT` — that is what rewardkit reads, and every dimension
inherits it from the verifier environment. A `judge.toml` therefore carries only its own
grading SHAPE: `mode`, `timeout`, `isolated`, `temperature`, `weight`,
`prompt_template`, its `[[judge.mcp_servers]]`, and its `[[criterion]]` blocks. Do NOT
report a `judge.toml` as unpinned, or as missing a model / driver / reasoning effort,
because it does not name one — that is the correct shape. A `judge.toml` that DOES name
one of those three is the defect: it is a second home for a value with one owner, and it
drifts the first time the model is bumped in `task.toml` and not there.

`tasks/<slug>/` — **this is the complete, closed list. Nothing else may exist here.**

```
task.toml                         config: identity, agent/verifier wiring, judge
                                  driver/model/effort (the ONLY place these live)
instruction.md                    the prompt — the ONLY thing the agent is told
environment/
  Dockerfile                      the AGENT image: runtime + pre-installed deps + the app dir
  assets/**                       read-only inputs the app needs (seed data, media); some ship none
solution/
  solve.sh                        the ORACLE entrypoint: installs the reference app for grading
  <reference app files>           the reference application itself (server and/or static files)
tests/
  Dockerfile                      the VERIFIER image: browser + Playwright + judge + rewardkit
  test.sh                         verifier entrypoint: safely launch the app, gate on liveness, grade
  reward.toml                     the top-level aggregate block(s) that combine the dimensions
  <dimension>/judge.toml          one browser-judge dimension (prompt + criteria + weight)
```

A `README.md` is permitted (human design note, never shipped to the agent). A copy of
the QC rubric (`task-implementation.toml`, optionally under `rubrics/`) may sit with the
task — it is never shipped to the agent. Anything else at the task root is a defect (see
`task_folder_holds_only_task_files`).

You will typically have THIS file plus the task folder. You will NOT have sibling tasks,
a taxonomy spreadsheet, or a project scorecard. Do not fail a task for lacking those, and
do not assume a sibling's stack, port, dimension names, or credentials. Dimension
directory names are chosen per task — they need not be `functional` / `render` /
`aesthetic` / `polish`; read whatever `tests/<dimension>/judge.toml` files this task
actually ships.

## This rubric is archetype-agnostic — apply it to whatever THIS task actually is

WebDev tasks span many archetypes: static marketing/portfolio pages; client-only canvas
or board GAMES; generative-art / animation pieces; data-visualization and chart tools;
media players; chat and messaging UIs; productivity/editor clones; and full-stack CRUD
apps, dashboards, and admin panels with a backend, authentication, and a database. These
differ in what they even HAVE: some have a backend and a database, many are purely
client-side with no server state; some have auth and roles, most have none; some persist
across reloads, many are stateless; some ship seed data or media, some ship nothing but
the ask; some are deterministic, games and generative art are intentionally random.

DO NOT invent a requirement the instruction did not make. Auth, persistence, a backend, a
database, or seed data are REQUIRED only when this task's instruction (or the plain nature
of the product it asks for) calls for them. A criterion that assumes a capability the task
legitimately does not have is `not_applicable` for that task — say WHICH capability is
absent and why. The universal requirements that hold for EVERY archetype are only these:
the app loads and renders real, working content (not a blank page, an error, or a static
non-functional shell); the graders actually exercise the core behavior that defines the
product; a correct reference scores high and a do-nothing / faked app scores low. Note that
serving same-origin is NOT a universal requirement here — network is public (see NETWORK
POLICY below). When you mark a criterion `not_applicable`, still confirm the UNIVERSAL floor
holds by some OTHER criterion — never let "no backend" become a way for a non-functional app
to escape grading.

**App-level randomness is not a determinism defect.** A game, a shuffle, a particle
system, or any app the instruction asks to be random is SUPPOSED to vary its output, and
the judge grades its BEHAVIOR (is it playable, does it animate, do the rules hold) rather
than an exact pixel or value. Do not fail such a task under any determinism criterion for
that intrinsic randomness. The determinism criteria police the SCORING path (the pinned
model in `task.toml`, the per-dimension temperature, the prompt) and the frozen
reference — not the app's own legitimately random output, and not the verifier having
network access.

## NETWORK POLICY — INTERNET IS ALLOWED IN THIS PROJECT

**Read this before judging any network-related criterion.** This project runs with PUBLIC
network access. Both the AGENT environment and the VERIFIER environment use
`network_mode = "public"`, and that is **CORRECT** — it is what this project wants, not a
defect. Concretely, for every criterion:

- a `public` agent network and a `public` verifier network are the expected, correct posture;
- **NO** `allowed_hosts` allowlist is required on the verifier;
- the app **MAY** fetch external browser assets (CDN scripts, web fonts, remote images) and
  call external APIs at build time and at grade time — **same-origin is NOT required**;
- an app that fetches off-origin works fine at grade time, so it is never a floor case and
  never an "unreachable capability";
- a reference or a submission that installs a package or fetches at start is not a defect.

Do NOT report any of the following as a problem: a `public` network mode, a missing
allowlist, an external CDN/font/script/image/API fetch, or a lack of same-origin/offline
operation. A criterion or judge gate that still *demands* same-origin is itself the defect —
it false-FAILs correct apps that use a CDN.

The only network-adjacent things that can still be real defects are unrelated to access: a
floating/unpinned package or image version that changes behavior between builds, a
secret-shaped literal that should be a `${VAR}` template, or the judge model/credentials
being wired inconsistently — which now means a missing `REWARDKIT_*` key in `task.toml`,
or a `judge.toml` that contradicts it, NOT a `judge.toml` that simply inherits it.

## The two environments — the single most important thing to internalize

A task runs in TWO different containers, and a defect is usually a fact that is true in one
and false in the other:

- **BUILD-TIME** (agent image, from `environment/Dockerfile`): PUBLIC network is available,
  the runtime deps pre-installed, and any inputs mounted read-only at `/assets/...`. The
  agent builds the app under `/app` here. `/assets` EXISTS here (when the task ships assets
  at all).
- **GRADE-TIME** (verifier image, from `tests/Dockerfile`, run as a SEPARATE container):
  has the browser, Playwright, the judge, and rewardkit — but it does NOT contain
  `/assets`, does NOT contain the agent image's global deps unless its own Dockerfile also
  installed them. It has PUBLIC network access. `test.sh` takes the submitted app, copies
  it, and launches it (typically as an UNPRIVILEGED user) with whatever env IT chooses (a
  port, a storage path), then gates on a liveness probe before any judge runs. The exact env
  vars, launch command, and probe are per-task — read THIS task's `test.sh` for them.

The consequences you must actively check for (each applies only insofar as the task HAS
that capability — a static, stateless, asset-free app simply has fewer of these surfaces):

- the app must be SELF-CONTAINED: anything it needs at runtime (seed data, media, config)
  must be BAKED IN at build time, because `/assets` is gone at grade time. An app that
  reads `/assets` at runtime works for the agent and scores 0 when graded;
- if the app takes runtime config from env (port, storage path), it must honor the env the
  verifier sets, OR the verifier must match the literal contract the instruction gave the
  agent — a divergence means a correct, instruction-following app binds the wrong port,
  writes to the wrong place, is non-durable, or crashes;
- whatever `test.sh` gates on for liveness must be something a correct app necessarily
  serves, or the instruction must have asked for it — otherwise the liveness gate zeros a
  correct app.

Same-origin is deliberately NOT on that list: network is public at grade time, so the app
may fetch CDN scripts, fonts, images, or external APIs off-origin without penalty.

`verifier_and_instruction_agree_on_the_runtime_contract` is the criterion that polices
this; keep the two environments in mind for every other criterion too.

## The organizing principle — the two-sided gate

This suite is training data for RL. A task is only useful if its reward is SOUND in BOTH
directions. Every criterion protects one of two facts:

- **ORACLE high** — the reference app in `solution/` scores near the top: the task is
  buildable and the judges accept a correct, complete application.
- **FLOOR low** — nothing an agent can produce without doing the real work scores well:
  not a blank page, not a static mock, not a client-only fake, not a keyword-stuffed
  shell, not a polite refusal.

When you judge any criterion, say which side of that gate a defect breaks: which correct
app is wrongly scored low, which lazy/faked app is wrongly scored high, or which run
crashes before either can happen.

## What counts as "required" — apply this everywhere

A behavior, value, or format is required of the agent ONLY when `instruction.md` states it
(including the runtime contract it states), or when it is an unambiguous professional
default for the product asked for. None of the following makes something required, and a
criterion that enforces one is a defect:

- the reference app's incidental choice — its routes, its DOM structure, its exact copy,
  its color values — where the instruction is silent;
- a name that only exists in `tests/` or `solution/`;
- your own inference about what was probably intended.

The judges are explicitly told to grade OUTCOMES, not routes/selectors/wording — hold the
rubric to the same standard.

## Method — miss nothing, but spend tokens where they matter

0. Name THIS task's archetype in one line (static page / client-only interactive /
   stateful client storage / authenticated server-backed / game / generative / media /
   viz / other). Every `not_applicable` below must cite that line. Do not demand auth, a
   database, seed data, or persistence of an archetype that has none.
1. Read `instruction.md`. Write down (a) the DELIVERABLES the persona asks for — every
   feature, screen, workflow, and quality ask — and (b) the RUNTIME CONTRACT it states,
   taking only the parts that apply to this app (app path, start command, port, served
   file/entry, any storage/DB path, any seed/asset path, any demo accounts). Network is
   PUBLIC in this project, so there is no no-network constraint to state or to check for.
   In this suite the runtime contract in the
   prompt is REQUIRED of the agent, because it is the interface the verifier assumes. As
   you read, mark any AMBIGUITY a criterion could ride on — a graded quantity with no
   defined unit, a phrase with two competent readings, an ask the prompt only directs as
   method — because a criterion built on it false-FAILs many correct apps at once.
2. Read `task.toml` as the run wiring, and `environment/` as the world the agent wakes in.
   If the task ships assets, open them and record their schema, entity names, and volumes;
   if it ships none, note that and move on.
3. Read every `tests/<dimension>/judge.toml`: the prompt, the global gate, and every
   `[[criterion]]`. Write down what each criterion pays for and its weight.
4. Treat `solution/` DIFFERENTLY — see the efficiency rule below. Do NOT read every line
   of the app or the reference HTML. Establish COVERAGE, not correctness line-by-line.
5. RECONCILE IN ALL DIRECTIONS: a deliverable with no grading dimension; a criterion with
   no deliverable behind it; a criterion whose expected value the seed contradicts; a
   runtime fact that disagrees between files; a LATER dimension that assumes the seed is
   still pristine after an EARLIER dimension mutated it. Each is a separate finding.

## Judge each criterion as its own critical block — re-read its files

The read above builds your map of the task; it does not settle any criterion. Treat EVERY
criterion as a self-contained critical block: before you write its verdict, go BACK to the
specific file(s) that criterion governs and re-read the relevant part with that criterion's
question in mind. Do not judge a criterion from memory of an earlier pass or from a general
impression of the task — the defect a criterion exists to catch is usually in a detail you
skimmed the first time, and each criterion asks a DIFFERENT question of the same files. The
task is judged one criterion at a time; a criterion is never waved through on the strength
of having read the file once for something else. A criterion judged without re-opening the
file it governs is an unrun check: return `not_applicable` and say the read was not
performed, rather than passing it on memory.

## Efficiency rule — the solution folder and other large files

The reference application (`solution/` entry files, the reference HTML/JS, any bundle) and
some fixtures can be LARGE, and reading them line by line burns tokens for little signal.
For `solution/` you are checking COVERAGE and PLAUSIBILITY, not auditing the code:

- Skim structure, not every line: the set of routes/handlers, the feature sections in the
  UI, the tables/entities seeded, the install steps in `solve.sh`. A grep-level pass over
  route/handler declarations and feature labels is enough to decide coverage.
- Decide the question each solution criterion actually asks: "does the reference plausibly
  COVER every deliverable the instruction asks and every criterion the judges grade, and
  does it honor the runtime contract" — a presence/coverage judgment, not an execution or a
  line-by-line correctness proof.
- You are NOT required to run the app or reproduce a score. The oracle/no-op validation leg
  runs the reference separately; do not duplicate it or claim a score you did not see.
- If a file is too large to read in full, say so, sample it (head + the relevant sections),
  and reason from the sample — never report a solution file as verified when you only read
  its name. Prefer `not_applicable` with the reason over a guess.

Apply the same restraint to any oversized fixture: sample and reason, do not inline it whole.

## Enumerate every instance — a criterion is a lens, not one slot

A criterion is a lens you pass over the WHOLE task, not a single slot that holds one
finding. When you apply it, report EVERY artifact that trips it — every dimension criterion,
every judge prompt, every fixture record, every runtime-contract value — each with its own
quoted evidence and its own gate reasoning. A rubric with four un-cued criteria has four
findings under `dimensions_cover_every_graded_requirement`'s mirror, not one; stopping at
the first offending criterion and moving on is a miss as real as never having looked.

A single task artifact can also trip SEVERAL criteria at once, and each owns its own
finding. One judge criterion that names two credit bars AND grades an outcome the prompt
never asked for is a finding under `criterion_description_is_self_consistent` AND under
`no_criterion_grades_the_unrequired`; a dimension prompt that omits the browser gate AND
names a stale credential is a finding under
`global_browser_gate_is_present_and_correct_in_every_dimension` AND under
`dimension_prompts_are_accurate_and_consistent`. Record it under each — never let a finding
on one criterion stand in for the finding another criterion owns, and never decide "I
already flagged that criterion once" and drop the second angle.

So within a single criterion's verdict, if more than one distinct issue is present, list ALL
of them — most critical first — each with separate evidence. Do not merge two defects into
one line, do not drop the quieter defect because a louder one shares the criterion, and do
not let a FAIL you have already reached end the search through the rest of the task. The
pass bar folds several smaller defects into one FAIL verdict; the EXPLANATION behind that
verdict must still enumerate every one, because each is a separate thing the author has to
fix, and a critical defect left off the list because a lesser one was already named is the
failure this gate exists to prevent.

## Track findings on a scratch file, one section per criterion — so no issue is missed

Keep a scratch file OUTSIDE the task directory (for example `/tmp/review_scratch.md` — never
inside the task, which you must not modify). Before you start judging anything, create one
section in it headed by EACH criterion's name from `task-implementation.toml`, up front, in
order. As you read the task — even while you are reading for a DIFFERENT criterion — the moment
you notice a defect, discrepancy, or open question, file it under the section for the criterion
it belongs to: the quoted evidence, the file it came from, the witness, and its effect on the
gate. A defect spotted while reading `instruction.md` for one criterion is still on record when
you reach the criterion it actually belongs to.

Before you emit any verdict, walk the scratch file section by section and confirm that (a) every
criterion's section has been filled in — a list of its issues, or an explicit "none found,
re-read <files>" — and (b) every stray note has been moved under the criterion that owns it. Your
final written review for each criterion is that section, cleaned up. A criterion whose section you
never opened has not been reviewed — do not hand it a verdict from memory. An issue is either
sitting under its criterion in the scratch file or it is lost; this file is what guarantees no
issue is missed. A real defect that goes unreported because you forgot it by the end is the same
failure as never having found it.

## Standard of evidence — name the witness

Findings are only reportable with a concrete witness:

- **False-PASS witness** (coverage / floor finding): describe a specific app or submission
  that satisfies every existing criterion while skipping the outcome you say is ungraded, or
  that scores well while having done no real work. If you cannot describe one, the outcome
  is already covered — do not report it.
- **False-FAIL witness** (strictness finding): describe a specific correct, complete app a
  competent agent would plausibly build that a criterion (or the graders) would score below
  full marks. If you cannot, the check is defensible — do not report it.

When you propose a fix, respect the floor: loosening a check so it also passes a faked or
empty app is not a fix — it trades a false FAIL for a false PASS. Loosen to the weakest form
that still fails a lazy/faked app.

## Greps over-flag, and other false-finding traps

Read the sentence before calling a leak. Argue against each of your own findings: is the
information really absent, or is it in the seed / the Dockerfile / another dimension you did
not open? Is it a real defect or a convention this format legitimately uses (naming `/app`,
the port, and the demo accounts in the prompt is REQUIRED here, not a scaffolding leak)?
Drop whatever does not survive. Never present an unrun check as passed: if an input you
needed was unreadable, return `not_applicable` and say which one.

## The pass bar

FAIL when the criterion is materially violated: one defect that makes the task unrunnable,
unsolvable, trivially satisfiable, or wrong, or several small defects together. PASS when it
holds — a single cosmetic nit does not fail a criterion, but say it. Never pass leaving a
real defect unmentioned; never fail without naming one. Mark `not_applicable` only where the
criterion's own guidance allows it, or where an input you needed was unreadable — say which.

## How to write the finding — plain language, ONLY what is wrong

The reason you write is read by a human who needs to FIX the task fast. Write it so a
non-expert understands the problem in one read. Follow these rules for every criterion's reason:

- **Say only what is WRONG.** Do NOT narrate what is correct. Skip lines like "X is set
  correctly", "the model is pinned", "everything else checks out". If the criterion PASSES with
  no defect, the reason is simply one short line such as "No issues found." — nothing more. If it
  FAILS, list ONLY the problems. Never write the "this is right, this is right, however this is
  wrong" pattern — cut straight to the wrong part.
- **Explain it like I'm five (ELI5).** Use plain, everyday words and short sentences. Say what is
  broken and what it causes, in terms anyone could follow. Avoid jargon; when a technical term is
  unavoidable, add a few plain words saying what it means. A reviewer skimming twenty findings
  should grasp each one instantly.
- **Always name the file (and line if you have it).** Start each issue with the file it lives in,
  e.g. "`task.toml` — ..." or "`tests/functional/judge.toml:42` — ...". A finding with no file
  name is not actionable; always point to where the problem is.
- **One issue per bullet.** If a criterion has several problems, use one short bullet each, most
  important first. Keep each bullet to a sentence or two: what is wrong → where it is → what it
  breaks. Quote the offending text briefly when it helps locate it.
- **No fix essays.** A short "what it breaks" is enough; do not write a remediation plan.

Example of the WANTED style (a FAIL):
> - `task.toml` — the app's start port and the port the grader opens don't match (app uses 3000,
>   grader opens 8080), so a correct app looks dead to the judge and scores 0.
> - `tests/render/judge.toml` — this dimension never tells the judge to open the app in the
>   browser, so it could score from guesswork instead of the real page.

Example of what to AVOID:
> The port is defined in task.toml and it is set to 3000 which is good. The Dockerfile is pinned
> correctly and the model is wired properly. However, the grader opens port 8080...

(Cut everything before "However" — only the problem remains.)

## How similar criteria differ — do not fail the same defect twice

Several criteria look at the same files from different sides of the gate. Name the defect on
the criterion that owns it, and mention the cousin rather than copying the write-up:

- `instruction_states_deliverables` ↔ `dimensions_cover` ↔ `solution_covers` — was it
  asked? / is it graded? / does the reference have it?
- `verifier_and_instruction_agree` vs `cross_file_runtime_contract` — a hidden assumption
  the prompt never stated / a stated value that drifted.
- `grading_wiring` vs `binary_and_likert_fit_the_ask` — schema/types parse / the type
  matches the kind of ask.
- `global_browser_gate` vs `floor_is_low` vs `gates_apply_before_shaping` — gate text
  present and scoped / cheap apps actually score ~0 / gate zeros style.
- `judge_prompts_drive_the_browser` vs `dimension_prompts_are_accurate` — judge told to open
  the live URL / the prompt describes THIS product.
- `dimension_and_criterion_weights_are_honest` vs `reward_ranking_is_monotone` — are the
  shares deliberate? / do those shares invert good vs bad?
- `plural_asks` vs `later_dimensions_tolerate_earlier_mutations` — one criterion's
  first-match trap / cross-dimension seed-count trap.
- `criteria_are_outcome_based_and_browser_decidable` vs `criterion_description_is_self_consistent`
  — can the judge decide it by looking? / does the criterion's own text give the judge one
  bar or two?
