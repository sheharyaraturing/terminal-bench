# WebDev deterministic checks

Every file here is a standalone check script, invoked by the autoreviewer as
`<check> <task-dir>` with the project root as the working directory
(`core/deterministic.py`). Contract:

- **exit 0 = pass**, non-zero = fail
- print `FAIL <path>: <reason>` for each failure, `NOTE ...` for advisory
findings that should not block
- collect every failure before exiting; never fail-fast on the first

`project.toml` sets `include_common = false`: the repo-root `checks/` common set
does not run. It is written for terminal-bench conventions this project does
not follow (canary GUIDs, the "You have N seconds" instruction suffix,
`terminal-bench/<slug>` package names, `author_name` metadata), and suppressing
those needed six no-op shadow files that checked nothing and read as clutter.
Two of its checks also contradicted the severity rule below by hard-failing
what this suite reports as advisory — `check-dockerfile-platform.sh` on a
`--platform` pin, and `check-task-slug.sh` on any slug with more than three
hyphen-separated tokens. Both would block a legitimate task.

The rules from that set worth keeping were absorbed rather than dropped — see
**Absorbed from the common set** at the end.

## Running them

```bash
checks/run-checks bazaarbridge-marketplace   # one task
checks/run-checks --all                      # every task
checks/run-checks fleetops --only rubric     # checks matching a substring
checks/run-checks --list                     # what would run, and from where
```

Exit status is 0 only when every check passed. `run-checks` delegates to
`core.deterministic.run_deterministic`, so it reports exactly what the
autoreviewer runs. **It has no** `.py` **extension on purpose** — project checks are
discovered with `require_prefix=False`, so any `.py` or `.sh` here is executed
as a check, and a `run-checks.py` would run the whole suite from inside a suite
run. The same rule is why there is no shared `_lib.py`.

**Every check is self-contained.** Each script carries its own copy of the
helpers it needs in an `# --- inlined helpers ---` block below its docstring.
The cost is duplication: a fix to a shared helper must be applied per file. The
tunables stay environment-overridable (`WEBDEV_ORGS`, `WEBDEV_AGENT_MAX_SEC`,
`WEBDEV_VERIFIER_SOFT_CAP_SEC`), which keeps one knob per value.

---



## FAIL vs NOTE — the severity rule

A failing check blocks the task and stops the trainer being paid. That makes a
false positive far more expensive than a missed finding, so the bar for `FAIL`
is deliberately narrow:

> **FAIL only when the condition is mechanically certain AND the author would
> agree it is a bug.** If a competent author could look at it and say "I did
> that on purpose", it is a `NOTE`.

Concretely, `FAIL` covers: a file that must exist and does not, TOML/JSON that
does not parse, a value that contradicts another value in the same task (model
drift between `task.toml` and a `judge.toml`, a segment naming a criterion id
that is not in the rubric, an oracle that never creates the file the verifier
demands), a timeout ordering that guarantees a SIGKILL, a committed credential,
and grading machinery leaking into the agent's brief.

`NOTE` covers everything that is a judgment: resourcing (`memory_mb`, `cpus`),
network policy, security hardening of the harness pattern, prompt-wording
preferences, arbitrary thresholds (criteria counts, word counts, prompt
length), and any heuristic that cannot separate a real problem from a valid
alternative — build-only versus runtime dependencies, a criterion id that
collides with a component name, a liveness path the prompt does not mention.

Nothing is deleted by this rule; downgraded findings still print, and the
reviewer still sees them. They just do not block.

### Regression testing

Two properties are checked whenever these scripts change:

- **No false positives.** Two synthetic but entirely valid tasks are run
through the whole suite and must come back clean: a client-only canvas page
with no backend, no seed, no accounts and no dependencies, and a
Flask/SQLite app with sign-in on a non-Node stack. Both exist to catch rules
that quietly assume Node, npm, a backend, seed data, or auth.
- **Detection is preserved.** 44 single-defect mutations are applied one at a
time across both shapes, with the unmutated task's own failures subtracted as
a baseline — without that subtraction a task that already fails credits every
mutation with a catch it did not cause. 37 mutations are caught as failures;
the other 7 are the deliberately-advisory rules above and surface as notes.

---



## Two task shapes

Checks dispatch on which verifier convention a task uses, detected from the
filesystem**. Conflating them would either wave through a broken current-format
task or fail the earlier ones for lacking fields their runtime never reads.**


|                | **dimensions** (current)                                                         | **browser-rubric** (earlier)                |
| -------------- | -------------------------------------------------------------------------------- | ------------------------------------------- |
| reference      | `tasks/bazaarbridge-marketplace`                                                 | `fleetops`, `torquebay-enterprise`          |
| detected by    | `tests/<dim>/judge.toml`                                                         | `tests/rubric/browser/browser.toml`         |
| rubric         | one `judge.toml` per graded dimension, each with an **inline** `prompt_template` | one `browser.toml` + a `prompt.md`          |
| scoring        | `tests/reward.toml`, weighted mean across dimensions                             | computed in `tests/test.py`                 |
| verifier       | **separate** container from `tests/Dockerfile`                                   | **shared** with the agent                   |
| entrypoint     | `tests/test.sh` → `rewardkit /tests`                                             | `tests/test.sh` → `tests/test.py`           |
| judge          | `codex` / `openai/gpt-5.6-luna`                                                  | `claude-code` / `anthropic/claude-sonnet-5` |
| org            | `codearena/<slug>`                                                               | `webdev/<slug>`                             |
| agent network  | `no-network`, deps baked into the image                                          | `public`                                    |
| app entrypoint | fixed by `instruction.md`, enforced in `test.sh`                                 | discovered from `APP_MANIFEST.md`           |


`check-required-files.py` emits a NOTE on every browser-rubric task pointing at
the current format, so a migration backlog stays visible.

---



## Layout & identity



### `check-task-layout.py`

The task directory must be a slug-named **direct child of** `tasks/`.
`core/registry.py`'s `list_tasks()` enumerates `tasks/*` one level deep and
takes each directory name as the task id. A task nested deeper is invisible to
the harness, and the wrapper directory is surfaced as a task id with no
`task.toml`. A space in the name additionally splits into two bogus paths in
every bash common check.

### `check-task-name.py`

`[task].name` must be `<org>/<dirname>` with org in `{codearena, webdev}`. The
name is the published id; a drifted last component means a rename that did not
propagate. NOTEs when a shape uses the other shape's org — usually a
half-finished migration.

### `check-required-files.py`

The layout for the detected shape, plus: no `NOTES.md` / `SOLUTION.md` /
`ANSWERS.md` / `.env`, and at least two graded dimensions (a single one
collapses the reward to one judge's opinion).

### `check-no-stray-files.py`

No zips, authoring documents, built `.db` files, `.DS_Store`, `node_modules/`,
`dist/`, or saved trial output (`result.json`, `trajectory.json`,
`<slug>__xxxxxxx/`). A saved trajectory is a working solution sitting next to
the thing being graded. NOTEs a file in `tests/` that nothing reads — but not
`Dockerfile` or `reward.toml`, which the harness consumes by discovery.

### `check-no-placeholders.sh`

No `CHANGE-ME` or `{{name}}` markers. A task still carrying scaffolding parses,
builds, and grades — it just grades the wrong thing.

---



## Configuration



### `check-task-toml.py`

Shape-independent: `schema_version`, `[task]` name/version/description/keywords,
`[metadata]` category/difficulty, positive timeouts, `[environment]`
cpus/memory, `[verifier.env]` judge selection, and `artifacts` **not** nested
under `[verifier]` (Harbor reads it from the top level and silently drops it
there). `memory_mb >= 4096` because Chromium, the app, and the judge share one
container; below that the judge is OOM-killed and every criterion scores 0 —
which looks exactly like a bad submission.

Dimensions shape additionally requires `environment_mode = "separate"`, a
declared `docker_image`, and `network_mode = "allowlist"` **with**
`openrouter.ai`. The judge reads pages the submission wrote; an unrestricted
verifier turns a prompt injection into outbound network access.

Browser-rubric shape additionally requires top-level `artifacts` including
`/app`, the `ANTHROPIC_*` gateway block, `network_mode = "public"` on both
phases, and `authors` / `difficulty_explanation` / `task_id`.

### `check-timeout-hierarchy.py`

The nesting that stops a judge being SIGKILLed mid-session — the one
configuration mistake that turns a working task into a silent zero, because the
only reward left on disk is the 0.0 placeholder, indistinguishable from a
submission that failed everything on the merits.

- dimensions: **sum** of the per-dimension `[judge].timeout` < the
`timeout N rewardkit` guard in `test.sh` < `[verifier].timeout_sec`. The sum
matters because dimensions run sequentially inside one rewardkit invocation;
a per-dimension comparison passes while the run as a whole overruns.
- browser-rubric: `[judge].timeout` < `REWARDKIT_TIMEOUT_SEC` <
`[verifier].timeout_sec`.

Also caps `[agent].timeout_sec` at 5h and NOTEs a verifier budget past 10h.

---



## The rubric



### `check-rubric-schema.py`

Per dimension: the judge driver and model must match `REWARDKIT_JUDGE` /
`REWARDKIT_MODEL` (a per-dimension drift means the reward blends two graders
nobody meant to compare); `mode = "batched"`; `isolated = false`;
`temperature = 0` — this score is a training reward, and a sampled judge
makes the same submission score differently on a re-run; a positive dimension
`weight`; and a `prompt_template` containing `{criteria}`. Without that
placeholder the judge is handed a prompt with *no criteria* and scores on
nothing.

Criteria must be `binary`, or `likert` with an explicit integer `points` —
RewardKit defaults an unrecognised type to binary and a likert scale to 5
points, so a typo silently collapses a graded scale to pass/fail. Ids must be
unique (a duplicate overwrites the earlier verdict) and `name` must equal `id`.

### `check-rubric-prompt.py`

Three language families every browser-judge prompt must carry:

- **Prompt-injection defense** (hard fail). Everything the judge sees —
rendered text, source, network payloads, error strings — is authored by the
thing being graded, so a submission can simply ask for a good score in its own
UI. NOTEs a defense that names only a documentation file and leaves the other
channels uncovered.
- **Global browser gate** (dimensions shape). A stated prerequisite that zeroes
the dimension, so a blank or broken app is not scored criterion by criterion
on absent evidence.
- **Honest failure**, and for the single-session shape a **budget-exhaustion
rule**: a judge that runs out of turns must mark the criteria it never
attempted as failed. Summarising them instead is a fabricated pass — a wrong
number that looks like a right one.



### `check-reward-schema.py`

`tests/reward.toml`: a `[[reward]]` block with a name and an explicit
aggregation. Get this wrong and the task still runs, still calls every judge,
and still writes a reward — just not the one the dimension weights describe.
NOTEs anything but `weighted_mean`, which is the only aggregation that leaves a
training policy a gradient.

### `check-rubric-segments.py`

Browser-rubric only. `segments.json` ids must exist in `browser.toml`, appear
once, and cover every criterion — `test.py` is silently forgiving here, and a
single id typo reverts a 33-segment run to the one-big-session configuration
segmenting exists to prevent.

---



## The verifier



### `check-verifier-contract.py`

A reward on **every** exit path. Without one the trial is an infrastructure
error rather than a scored 0.0 — thrown away instead of counted, which quietly
biases the benchmark toward submissions that happen not to crash the verifier.
No `exec` (it replaces the shell, so the trap never runs); no `set -e` without a
`trap ... EXIT` (that is the exact path the fallback covers); a readiness probe
before grading; and for the browser-rubric shape a database wipe and no reading
of `/solution`.

### `check-verifier-sandbox.py`

The verifier holds a live `OPENROUTER_API_KEY`, the rubric, and network reach
to the gateway — then starts a server the submission wrote.

- **Credentials.** A server started with the verifier's environment inherited
can read the key out of `os.environ` and post it anywhere. Costs nothing to
prevent (`env -i` with an explicit allowlist) and leaves no trace when
missing.
- **The rubric.** A submission that can read `/tests` knows the criteria it is
about to be judged against.
- **The host.** A server running as root can rewrite the reward file.

Also NOTEs a missing symlink rejection and running `/app` in place rather than
from a copy.

### `check-solve-contract.py`

The oracle must install an app the verifier can grade — otherwise the task has
never been validated end to end, and a 0.0 for install reasons reads as "the
rubric is too hard". The strongest part is a cross-check: the `-f /app/...`
guards in `test.sh` are extracted and the oracle must create exactly those
files. Shape-specific expectations differ — the current format installs and
builds nothing (dependencies are baked, the agent phase is offline), the
earlier one must run npm and a frontend build.

---



## The images



### `check-dockerfiles.py`

`environment/Dockerfile` always, plus `tests/Dockerfile` for the dimensions
shape. Pinning (pip `==` and npm `@version` are hard failures; unpinned apt and
a floating `FROM` are NOTEs); no `--platform` pin; no `ENV NODE_ENV=production`
(npm's default `--omit` becomes `dev`, silently dropping the frontend
toolchain); no `COPY` of the solution or grading code; and a `CMD` that keeps
the agent container alive.

Whichever image the judge runs in must carry its whole toolchain — the driver
matching `REWARDKIT_JUDGE`, `@playwright/mcp`, `harbor-rewardkit`, Chromium, and
`PLAYWRIGHT_BROWSERS_PATH`. For a `codex` judge it must also write
`/root/.codex/config.toml`; codex resolves its model provider from that file, so
without it `OPENROUTER_API_KEY` is set and never used and every judge call fails
auth.

When `[environment].network_mode` is `no-network`, the environment image must
bake the app's runtime dependencies — otherwise the task is impossible rather
than hard.

### `check-assets-referenced.py`

Every `/assets/...` and `/instructions/...` path the brief names must exist
under `environment/` **and** be COPYed into the image. These are absolute
container paths: nothing in the repo resolves them and nothing fails at build
time. The agent meets the mismatch as a missing file it was told to read, which
reads to the agent as its own mistake.

---



## The brief



### `check-instruction-hygiene.py`

No unfinished placeholders; no rubric criterion id in the brief; no verbatim
12-word passage shared with any **criterion description**; no mention of
`/solution` or `solve.sh`.

The comparison is against criterion descriptions only, not whole prompts. A
judge prompt necessarily restates app facts the brief also states — the demo
accounts, the base URL, the seeded record names — because both sides need them.
That overlap is shared fixture data. What must never appear in the brief is the
wording of a criterion, which is what turns "infer the invariants" into
"implement this checklist".

---



## Absorbed from the common set

Turning the common set off would have lost a handful of genuinely useful rules.
They live here now:

| Common check | Where its rule lives now |
|---|---|
| `check-nproc.sh` | `check-trial-time-hermetic.py` — a bare `nproc` reads the host CPU count, so the same submission builds differently on different machines |
| `check-pip-pinning.sh` | `check-trial-time-hermetic.py` (trial-time scripts) and `check-dockerfiles.py` (images) |
| `check-trial-network-fetch.sh` | `check-trial-time-hermetic.py` — a fetch mid-trial turns a registry outage into a scored 0.0 |
| `check-verifier-tooling-baked.sh` | `check-trial-time-hermetic.py` — verifier tooling belongs in `tests/Dockerfile`, not installed at grade time |
| `check-separate-verifier.sh` | `check-task-toml.py` (mode, misplaced `artifacts`), `check-required-files.py` (`tests/Dockerfile`), `check-dockerfiles.py` (`COPY` into `/tests`, `RUN mkdir -p` for each artifact parent) |
| `check-dockerfile-references.sh` | `check-dockerfiles.py` (`check_no_leaks`), applied to real `COPY`/`ADD` instructions rather than to any substring — the common version passed `tests/test_*.py` to `grep` as a basic regex, where `_*` means "zero or more underscores", so it matched the plain text `tests/test.py` in a comment |
| `check-allow-internet.sh`, `check-no-allow-internet-true.sh` | `check-task-toml.py`, which rejects `allow_internet` entirely in favour of `network_mode` |

Deliberately **not** carried over: `check-canary.sh` (no canary convention),
`check-instruction-suffix.sh` (briefs are natural product requests),
`check-task-fields.sh` (different metadata vocabulary),
`check-task-package-name.sh` (`codearena/*`, not `terminal-bench/*`),
`check-task-timeout.sh` (the useful rule is the ordering, not a flat cap),
`check-dockerfile-sanity.sh` (apt pinning is a judgment),
`check-dockerfile-platform.sh` and `check-task-slug.sh` (both hard-fail
legitimate choices), and the checks that are inert here anyway —
`check-gpu-types.sh`, `check-pytest-version.sh`, `check-compose-host-binds.sh`,
`check-test-file-references.sh`, `check-ai-detection.py`.
