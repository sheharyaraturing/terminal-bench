# WebDev deterministic checks

Every file here is a standalone check script, invoked by the autoreviewer as
`<check> <task-dir>` with the project root as the working directory
(`core/deterministic.py`). Contract:

- **exit 0 = pass**, non-zero = fail
- print `FAIL <path>: <reason>` for each failure, `NOTE ...` for advisory
findings that should not block
- collect every failure before exiting; never fail-fast on the first

`project.toml` sets `include_common = true`, so the repo-root `checks/` common
set runs alongside these. Nine common checks are shadowed by same-named files
here (see **Overrides**).

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



## Overrides

These shadow same-named repo-root common checks. Two dispatch by shape, one is
a bug fix, six are documented no-op passes.


| Override                         | Common check expects                                                                                                                                                                     | Reality here                                                                                                          | Replaced by                    |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| `check-separate-verifier.sh`     | **dispatch** — separate mode always                                                                                                                                                      | dimensions tasks *are* separate, so it runs the common check; browser-rubric grades in the shared container by design | `check-verifier-contract.py`   |
| `check-test-sh-sanity.sh`        | **dispatch** — uv/npm isolation in shared mode                                                                                                                                           | runs the common check for dimensions; the browser-rubric `test.sh` installs nothing                                   | `check-verifier-contract.py`   |
| `check-dockerfile-references.sh` | **fix** — the common version passes `tests/test_*.py` to `grep` as a basic regex, where `_`* means "zero or more underscores", so it matches the plain text `tests/test.py` in a comment | same rule, applied to actual `COPY`/`ADD` instructions                                                                | —                              |
| `check-canary.sh`                | a canary GUID in every file                                                                                                                                                              | no canary convention; the solution is a whole application tree                                                        | —                              |
| `check-instruction-suffix.sh`    | the "You have N seconds…" line                                                                                                                                                           | briefs are in-world prose                                                                                             | `check-instruction-hygiene.py` |
| `check-task-fields.sh`           | terminal-bench metadata vocabulary                                                                                                                                                       | neither shape uses it                                                                                                 | `check-task-toml.py`           |
| `check-task-package-name.sh`     | `terminal-bench/<folder>`                                                                                                                                                                | `codearena/*` or `webdev/*`                                                                                           | `check-task-name.py`           |
| `check-task-timeout.sh`          | one 5h cap on agent **and** verifier                                                                                                                                                     | the agent cap holds; a browser-rubric verifier budget is a worst-case segment chain                                   | `check-timeout-hierarchy.py`   |
| `check-dockerfile-sanity.sh`     | apt pins **forbidden**                                                                                                                                                                   | the shapes disagree; neither answer is worth failing a task over                                                      | `check-dockerfiles.py`         |


---



## Coverage against the reference spec

All 39 checks in the circulated spec are covered. Fifteen were already
implemented under a different filename, so the spec's name is listed as an
alias rather than duplicated as a second script.


| Spec check                                       | Here                                                                            |
| ------------------------------------------------ | ------------------------------------------------------------------------------- |
| `check-required-files.py`                        | same name                                                                       |
| `check-no-placeholders.sh`                       | same name                                                                       |
| `check-no-extraneous-files.py`                   | `check-no-stray-files.py`                                                       |
| `check-instruction-content.py`                   | same name                                                                       |
| `check-instruction-hygiene.py`                   | same name                                                                       |
| `check-task-toml.py`                             | same name                                                                       |
| `check-task-name.py`                             | same name                                                                       |
| `check-timeouts.py`                              | `check-timeout-hierarchy.py`                                                    |
| `check-agent-dockerfile.py`                      | `check-dockerfiles.py`                                                          |
| `check-fixtures.py`                              | same name                                                                       |
| `check-environment-does-not-leak-solution.py`    | `check-dockerfiles.py` (`check_no_leaks`)                                       |
| `check-solve-sh.py`                              | `check-solve-contract.py`                                                       |
| `check-reward-schema.py`                         | same name                                                                       |
| `check-judge-toml-schema.py`                     | `check-rubric-schema.py`                                                        |
| `check-judge-prompts-name-the-url.py`            | `check-rubric-prompt.py` + `check-runtime-contract-strings.py` (port agreement) |
| `check-global-gate-present.py`                   | `check-rubric-prompt.py`                                                        |
| `check-verifier-dockerfile.py`                   | `check-dockerfiles.py` (`check_verifier_image`)                                 |
| `check-test-sh.py`                               | `check-verifier-contract.py` + `check-verifier-sandbox.py`                      |
| `check-runtime-contract-strings.py`              | same name                                                                       |
| `check-seed-literals-in-criteria.py`             | same name                                                                       |
| `check-probe-not-in-seed.py`                     | same name                                                                       |
| `check-demo-accounts-agree.py`                   | same name                                                                       |
| `check-assets-paths-resolve.py`                  | `check-assets-referenced.py`                                                    |
| `check-runtime-deps-in-both-images.py`           | same name                                                                       |
| `check-package-manifest-deps-preinstalled.py`    | same name                                                                       |
| `check-no-cdn-or-remote-assets.py`               | same name                                                                       |
| `check-injection-guard-present.py`               | `check-rubric-prompt.py`                                                        |
| `check-batched-independence-wording.py`          | same name                                                                       |
| `check-mcp-server-is-runnable.py`                | `check-rubric-schema.py` + `check-dockerfiles.py` (command installed)           |
| `check-no-trialforge-judge-keys.py`              | same name                                                                       |
| `check-solution-does-not-coach-judge.py`         | same name                                                                       |
| `check-seed-has-no-injection-payload.py`         | same name                                                                       |
| `check-no-host-paths.py`                         | same name                                                                       |
| `check-slug-is-clean.py`                         | `check-task-layout.py`                                                          |
| `check-task-version-and-resources.py`            | `check-task-toml.py`                                                            |
| `check-allowlist-matches-provider.py`            | same name                                                                       |
| `check-instruction-states-offline-constraint.py` | same name                                                                       |
| `check-toml-and-json-parse.py`                   | same name                                                                       |
| `check-no-literal-secrets.py`                    | same name                                                                       |


Beyond the spec, this suite also carries `check-app-manifest.py`,
`check-rubric-segments.py`, and `check-verifier-sandbox.py` (the credential,
rubric-readability, and privilege exposures of a verifier that starts
submission code), plus shape dispatch throughout so the earlier browser-rubric
tasks stay checked rather than exempt.

### Where this deviates from the spec, and why

`include_common = true`**, not** `false`**.** The spec recommends dropping the
repo-root set because five of its checks fail every webdev task. Those five are
shadowed by no-op overrides here, which leaves fourteen common checks running
that are worth having (`check-ai-detection`, `check-pip-pinning`,
`check-compose-host-binds`, `check-trial-network-fetch`, and so on). Turning the
set off would silently drop them.

`check-separate-verifier.sh` **is shadowed — but it dispatches.** The spec says
not to shadow it because webdev wants separate mode. That is right for the
current format and wrong for the earlier one, which grades in the shared
container by design. The override runs the real common check for
dimensions-shaped tasks and explains the exemption for browser-rubric ones, so
neither shape is waved through.

**Several rules are conditional on the task's own declared network.** The spec
assumes `no-network` throughout. Unpinned manifest dependencies and off-origin
CDN assets are hard failures when the run is actually offline or allowlisted,
and NOTEs when the task declares `network_mode = "public"` — where they are a
robustness cost rather than a broken run.