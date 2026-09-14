# WebDev deterministic checks

Spec of the mechanical checks this project needs. Scripts are not implemented
yet; this file is the checklist to implement against. Every check is a
standalone script, invoked by the autoreviewer as `<check> <task-dir>` with the
project root as the working directory (`core/deterministic.py`). Contract:

- **exit 0 = pass**, non-zero = fail
- print `FAIL <path>: <reason>` for each failure, `NOTE ...` for advisory
  findings that should not block
- collect every failure before exiting; never fail-fast on the first

`project.toml` should set `include_common = false`. The repo-root `checks/`
common set is written for terminal-bench conventions (canary GUIDs, the
"You have N seconds… do not cheat" instruction suffix, `terminal-bench/<slug>`
package names, `author_name` / `subcategory` metadata). WebDev tasks are
natural product prompts with a separate browser-judge verifier — those common
checks would fail every real task. Re-encode the *useful* common behaviors
here (separate verifier, `tests/Dockerfile` COPY into `/tests`, no literal
secrets) instead of running the shared set.

`_lib.py` (to add next to the scripts) is the shared helper: task-dir
argument, TOML loading, uniform `FAIL`/`NOTE` reporting. It is not a check;
running it directly exits 0 as a no-op.

These checks must work for **any** webdev task: static pages, client-only
games, generative art, dashboards, authenticated full-stack apps. Do not
require a backend, auth, seed data, a database, or a particular dimension
name (`functional` / `render` / …). Read THIS task's files for its contract.

---

## What belongs here vs the LLM rubric

Deterministic checks catch **silent mechanical failures** a grep or TOML parse
can prove: missing files, invalid schema, unpinned images, a judge.toml with
no Playwright server, `test.sh` that never writes a reward, CRLF in a shell
script, a model id that drifted between `task.toml` and a dimension.

They do **not** catch judgment: natural voice, whether criteria cover the
product, whether a hidden liveness probe is fair, whether the seed has enough
rows for a filter, whether a stub would score well. Those stay in
`rubrics/task-implementation.toml`. If a proposed check needs to understand
the app, it is not a check — it is a rubric criterion.

A useful rule: if the failure would look like **infra** (parse error, missing
reward file, image skip, auth to the judge provider) rather than a **quality**
opinion, it belongs here.

---

## Layout & scaffolding

### `check-required-files.py`

- **What:** the required task layout exists:
  - `instruction.md`
  - `task.toml`
  - `environment/Dockerfile`
  - `solution/solve.sh` plus at least one other file under `solution/` (the
    reference app — not an empty solve that copies nothing)
  - `tests/Dockerfile`
  - `tests/test.sh`
  - `tests/reward.toml`
  - at least one `tests/<dimension>/judge.toml` (directory name is free)
- **How:** path-existence checks. `environment/assets/` is **not** required —
  a static or client-only app may ship none. If `assets/` is missing AND
  `instruction.md` contains `/assets/`, that is a FAIL (prompt names a mount
  that does not exist). `README.md` and a copy of `task-implementation.toml`
  (optionally under `rubrics/`) are allowed. `NOTES.md` at the task root is a
  NOTE (must not ship — it becomes an answer key).
- **Why:** every later check assumes this skeleton. A missing
  `tests/Dockerfile` or `judge.toml` fails 20 minutes into a run as a Harbor
  error that names nothing useful.

### `check-no-placeholders.sh`

- **What:** no unfinished-template marker in text files: `CHANGE-ME`,
  `TODO`, `FIXME`, `XXX`, `<placeholder>`, `lorem ipsum`.
- **How:** recursive `grep -nI` over the task, skipping binaries
  (`*.bundle`, `*.db`, `*.sqlite`, `*.png`, `*.jpg`, `*.woff`, `*.mp3`,
  `*.mp4`, `*.wasm`). Collect every hit.
- **Why:** a task still carrying template scaffolding was copied and never
  finished. The judge would happily grade placeholder copy.

### `check-no-extraneous-files.py`

- **What:** the task tree is the closed list. FAIL on committed build residue
  (`node_modules/`, `__pycache__/`, `dist/`, `*.db` from a local run), OS/editor
  junk (`.DS_Store`, `.idea/`, `*.swp`), backups (`*.bak`, `*_old.*`), and
  extra top-level directories the format does not define. NOTE on a
  `package-lock.json` nobody's Dockerfile installs from.
- **How:** walk the tree against an allowlist of paths (the closed list in the
  rubric preamble). Do not recurse into allowed dirs looking for "too many
  files" — the reference app can be large.
- **Why:** residue leaks into the agent image or the upload; a committed
  `*.db` is stale state that makes the oracle non-reproducible.

---

## Instruction

### `check-instruction-content.py`

- **What:** `instruction.md` is finished prose: no `TODO`/`FIXME` inside it
  (overlap with placeholders is fine — this one also catches a stub), and at
  least `INSTRUCTION_MIN_WORDS` (default **40**) words. A NOTE if under 80
  words — many real product asks are short; a 12-word stub is not.
- **How:** word count + draft-marker regex with line numbers. Do **not** fail
  lowercase, fragments, missing Oxford commas, or informal grammar — that is
  the natural-voice bar and lives in the rubric.
- **Why:** placeholder scans catch unfinished *scaffolding*; this catches an
  unfinished *prompt*.

### `check-instruction-hygiene.py`

- **What:** the prompt names no grader machinery. Banned as word-boundary,
  case-insensitive matches (quote the line):
  - tooling: `rewardkit`, `playwright`, `codex`, `harbor`, `openrouter`
  - files: `reward.toml`, `judge.toml`, `test.sh`, `/tests`
  - rubric speak: `you will be scored`, `dimension`, `criterion`/`criteria`
    (as grading terms), `pass bar`, `oracle`, `verifier` (benchmark sense)
  - grader sentinels: `JUDGE-` prefixes and a standalone `Judge ` used as a
    probe name (the functional pattern of creating `Judge Customer` records
    belongs in the judge prompt, not the user prompt)
- **How:** regex over `instruction.md` only. Do **NOT** flag the product
  interface: `/app`, a port number, a start command, a storage path, a seed
  path, demo emails/roles, `localhost`, stack names (Node, Express, SQLite,
  React, …), or "do not install packages". Those are the runtime contract and
  are supposed to be there.
- **Why:** naming the grader makes the agent write to the rubric instead of
  building the product. False positives on ordinary English (`task`, `check`,
  `test` as in "test accounts") must be avoided — require a grader-context
  neighbor for ambiguous words, same trick trialforge uses for `time`/`memory`.

---

## task.toml & run wiring

### `check-task-toml.py`

- **What:** `task.toml` is valid TOML and carries the webdev run contract:
  - `schema_version = "1.4"`
  - `[task].keywords` includes `webdev` (NOTE if missing, not FAIL — a
    forgotten keyword does not break a run)
  - `[metadata].difficulty` and `[metadata].category` present
  - no borrowed sibling fields: `enabled_tools`, `persona`, `target_claims`,
    `MCP_SERVERS`, `LOCAL_TOOLS`, `GATEWAY_PORT`
  - `[environment].network_mode = "no-network"` (FAIL on `public`; NOTE if
    the key is absent)
  - `[environment].docker_image` is **not** set (Harbor would skip
    `environment/Dockerfile` — pre-installed deps and `COPY assets/` never
    happen)
  - `[verifier].environment_mode = "separate"`
  - `[verifier.environment].network_mode = "allowlist"` with a non-empty
    `allowed_hosts`
  - `[verifier.env].OPENROUTER_API_KEY` (or the provider key that matches
    `allowed_hosts`) is a `${VAR}` template, not a literal
  - `[verifier.env].REWARDKIT_JUDGE`, `REWARDKIT_MODEL` and
    `REWARDKIT_REASONING_EFFORT` are present and non-empty. These three are
    the judge's identity and `task.toml` is the ONLY place they are declared
    now — a `judge.toml` does not repeat them (see
    `check-rubric-schema.py`). Only presence is asserted; which driver, which
    model id and which effort are the task's own choice
  - any env value whose key looks like a secret (`key|token|secret|password`
    except documented demo passwords, which do not belong in `task.toml`
    anyway) is a `${VAR}` template
- **How:** `tomllib` parse plus field assertions. Collect every failure.
- **Why:** each rule is a measured silent failure. A prebuilt agent image
  skips the Dockerfile. A literal API key is a credential in git. A shared
  verifier lets the agent read `tests/`. An open verifier network is
  exfiltration + non-determinism. Missing judge env fails auth at grade time
  and looks like infra.

### `check-task-name.py`

- **What:** `[task].name`'s last path component equals the task directory
  name. A namespace prefix (`codearena/`, `webdev/`, …) is fine. FAIL if the
  prefix is a leftover from another suite (`trialforge/`, `toolathon/`,
  `terminal-bench/`, `context-mesh/`).
- **How:** string compare of the name suffix against the directory basename.
- **Why:** a mismatch is a rename that did not propagate — findable by
  directory, dangling by name in the logs.

### `check-timeouts.py`

- **What:** timeouts compose.
  - `[agent].timeout_sec` present and `>= 300` (NOTE under 900 — a full app
    build rarely fits in a few minutes; do not FAIL a focused static-page
    task with a short-but-positive budget)
  - `[verifier].timeout_sec` present
  - every `tests/<dim>/judge.toml` has `[judge].timeout` as a positive number
  - verifier timeout is **greater than** the sum of dimension judge timeouts
    (judges run sequentially) plus slack for liveness (default slack 120s).
    FAIL if `verifier.timeout_sec <= sum(judge.timeout)` — a dimension is
    silently truncated
  - if `test.sh` wraps rewardkit in `timeout N`, N must also exceed that sum
- **How:** parse `task.toml` + every `judge.toml`; regex `timeout <n>` in
  `test.sh`.
- **Why:** a correct app killed mid-grade scores 0 for no product reason. The
  nested-timeout bug is mechanical and easy to miss by eye.

---

## Environment (agent image + assets)

### `check-agent-dockerfile.py`

- **What:** `environment/Dockerfile` is a real agent image:
  - `FROM` is pinned to a tag (never `:latest`, never an untagged digest-less
    floating name)
  - `WORKDIR` is set (the prompt's app dir, typically `/app`)
  - the image does not `CMD`/`ENTRYPOINT` the app as PID 1 in a way that
    fights Harbor's agent (a `sleep infinity` / bash wait is the expected
    shape; FAIL a Dockerfile whose CMD is `node server.js` so the agent never
    gets a shell)
  - no build-time `git clone` / `curl | sh` from an unpinned live remote
  - package installs pin versions (`express@5.1.0`, not `express`)
- **How:** comment-stripped Dockerfile scan. Do not require Node, Python, or
  any particular stack — require pinning and a wait-shaped CMD.
- **Why:** `:latest` and unpinned deps make the task non-reproducible. An
  image that starts the app as PID 1 looks like a hung agent.

### `check-fixtures.py`

- **What:** every relative `COPY`/`ADD` source in `environment/Dockerfile`
  exists under `environment/`. If `environment/assets/` exists, the Dockerfile
  actually `COPY`s it (otherwise the seed is in git and absent in the
  container). JSON/CSV seeds under `assets/` parse (JSON via `json.loads`,
  CSV via a header-row read). No unpinned live clone.
- **How:** parse COPY/ADD (skip URLs and `${VAR}`), glob wildcards, parse
  structured seeds. Skip binary media — existence is enough.
- **Why:** a missing COPY source is a build failure deep in the pipeline. A
  seed the Dockerfile never copies is an empty-data run. Broken JSON is a
  crash at first boot.

### `check-environment-does-not-leak-solution.py`

- **What:** `environment/Dockerfile` does not `COPY` `solution/`, `tests/`, or
  a pre-built app bundle into the agent world. No file under `environment/`
  is named like a reference app (`reference.html`, `solve.sh`).
- **How:** Dockerfile COPY sources + a name scan under `environment/`.
- **Why:** the agent must build the app, not find it. A leaked reference is a
  floor of 1.0.

---

## Solution (oracle install)

### `check-solve-sh.py`

- **What:** `solution/solve.sh` is a real installer, not a stub:
  - has a shebang
  - parses (`bash -n`)
  - no CRLF line endings (`\r` before `\n` on the shebang/`set -e` line is a
    hard FAIL — the shell rejects `set -euo pipefail\r` and the oracle dies
    with a missing-reward error that names nothing)
  - non-trivial body (more than shebang + `set -e` + comments)
  - copies or writes into the app dir the prompt names (usually `/app`)
  - does not invoke the network (`curl`, `wget`, `npm install`, `pip install`)
    — the reference must use what the agent image pre-provides
- **How:** `bash -n`, byte scan for `\r`, regex for install/copy vs fetch.
  Follow a one-level wrapper (`solve.sh` → `solve.py`) the way toolathon does.
  Do **not** run the app and do **not** read the whole reference source — that
  is the rubric's coverage pass.
- **Why:** Harbor's OracleAgent runs `solve.sh`. A stub or a CRLF script
  makes the oracle permanently red and looks like a bad task. A solve that
  `npm install`s violates the same no-network rule the agent is held to.

---

## Verifier & browser-judge wiring

This is the webdev-specific cluster. Trialforge checks one `reward.toml` with
`[[criterion]]`. Toolathon checks `tests/<dim>/check.py`. WebDev checks
**many** `judge.toml` files plus a verifier image that must both *launch the
app* and *drive a browser*.

### `check-reward-schema.py`

- **What:** `tests/reward.toml` is the top-level aggregate, not a judge file:
  - at least one `[[reward]]` block with `aggregation = "weighted_mean"`
  - **no** `[judge]` table and **no** `[[criterion]]` (those belong in
    `tests/<dim>/judge.toml` — their presence here means a half-migrated
    trialforge file and the dimensions never run)
- **How:** parsed-TOML assertions.
- **Why:** rewardkit discovers dimensions from the tests tree and combines
  them with this aggregate. A `[judge]` here is the wrong format; `all_pass`
  at this top level would collapse the whole task to 0 unless every dimension
  is perfect — no gradient.

### `check-judge-toml-schema.py`

- **What:** every `tests/<dimension>/` directory (skip files at `tests/` root)
  contains a `judge.toml` that is structurally complete:
  - `[judge]` with: `temperature = 0`, a numeric `weight` `> 0`, a numeric
    `timeout` `> 0`. It does NOT carry `judge` / `model` /
    `reasoning_effort` — the judge's identity lives in `task.toml`'s
    `[verifier.env]` (`REWARDKIT_JUDGE` / `REWARDKIT_MODEL` /
    `REWARDKIT_REASONING_EFFORT`), which is what rewardkit reads. Their
    absence here is CORRECT and must not be flagged
  - `mode` and `isolated` must be PRESENT (FAIL if absent, or if `mode` is
    not a non-empty string / `isolated` is not a boolean) — without them
    rewardkit picks its own default and the dimension never chose how it is
    graded. Their VALUES are the task's call: `mode = "batched"` and
    `isolated = false` are the expected shape, and anything else is a NOTE,
    not a FAIL (a future task may split criteria). Never flag batched mode as
    a defect the way a text-answer suite would
  - `prompt_template` is a non-empty string: either the prompt inline, or the
    name of a prompt file beside `judge.toml` — both shapes are accepted and
    no particular filename is required. Whichever it is, the prompt text
    contains the `{criteria}` placeholder
  - at least one `[[judge.mcp_servers]]` with a `command` (the browser MCP).
    FAIL if the block is missing — the judge cannot open the app
  - at least one `[[criterion]]`, each with non-empty `id` and `name`, a
    numeric `weight` `> 0`, a non-empty `description`, and a valid `type`:
    `binary` (no `points`) or `likert` (has `points`)
  - criterion `id` values are unique **across the whole task**
  - a leftover `[judge].judge` / `model` / `reasoning_effort` is a FAIL
    whatever its value: contradicting `task.toml` means the file reads as if
    this dimension is graded by a different model than its siblings, and
    merely duplicating it means the two copies drift the first time the model
    is bumped in one place and not the other. One home for the value
- **How:** parse `task.toml` for the three `REWARDKIT_*` keys, then every
  `judge.toml`; set-compare ids. An empty dimension directory is a FAIL.
- **Why:** each rule is a silent zero. No MCP server → the judge never sees
  the app and scores from the prompt. No `{criteria}` → it grades the
  preamble alone. A likert without `points` scores unpredictably. A missing
  `REWARDKIT_*` key in `task.toml` means rewardkit picks the grader, not the
  task — and a re-run after a rewardkit bump grades with a different model.
  Duplicate ids collide in the score breakdown.

### `check-judge-prompts-name-the-url.py`

- **What:** every dimension `prompt_template` contains a local URL
  (`localhost` / `127.0.0.1` plus a port) and the string `Playwright` or
  `MCP` or `browser` (it tells the judge to drive the browser, not read
  source). The port in the prompt matches the port `test.sh` uses (see
  `check-runtime-contract-strings.py`).
- **How:** regex on each `prompt_template`. FAIL if no local URL. NOTE if
  there is no browser-tool cue.
- **Why:** without a URL the judge hallucinates a score. A port mismatch
  means the judge opens a dead socket while the app is bound elsewhere.

### `check-global-gate-present.py`

- **What:** every dimension prompt contains a global browser gate: a phrase
  that assigns 0 to every criterion when the page does not load / is blank /
  is cross-origin (look for `assign 0` / `score 0` / `every criterion` plus
  `same-origin` or `loads`). This is a **presence** check, not a quality
  check — whether the gate is correctly scoped for auth vs a public page is
  the rubric.
- **How:** regex over each `prompt_template`. FAIL if a dimension omits it.
- **Why:** a missing gate is the primary floor leak (a pretty static shell
  collects that dimension's marks). Wording quality stays with the rubric.

### `check-verifier-dockerfile.py`

- **What:** `tests/Dockerfile` can launch the app **and** drive the judge:
  - `COPY` or `ADD` into `/tests` (separate-verifier mode does not upload
    `tests/` — the image must own it). Same rule as the common
    `check-separate-verifier.sh`
  - `test.sh` is made executable (`chmod`)
  - a browser is installed (Playwright / Chromium string present)
  - the Playwright MCP (or whatever `[[judge.mcp_servers]].command` names)
    is installed — FAIL if the command in `judge.toml` does not appear in
    this Dockerfile
  - the judge CLI named by `REWARDKIT_JUDGE` (e.g. `codex`) is installed
  - `harbor-rewardkit` (or `rewardkit`) is installed, pinned
  - `FROM` tags are pinned (never `:latest`)
  - does **not** `COPY` `../solution` or the reference app into the verifier
- **How:** comment-stripped Dockerfile scan, cross-referenced against
  `judge.toml` MCP `command` and `task.toml` `REWARDKIT_JUDGE`.
- **Why:** grade-time is a different image. A dep only the agent image
  installed is gone; a missing browser means the judge cannot observe; a
  missing `COPY /tests` means there are no graders in the verifier
  container.

### `check-test-sh.py`

- **What:** `tests/test.sh` is a safe, always-scoring launcher:
  - shebang, `bash -n`, no CRLF (same as solve.sh)
  - invokes `rewardkit` (FAIL if not — Harbor then reports
    `RewardFileNotFoundError`)
  - writes a zero reward on failure paths (`reward.txt` / `reward.json` with
    `0.0`) — FAIL if there is no zero-reward write at all; NOTE if it is
    only on some paths
  - starts the submitted app (a language runtime / server command) and
    **gates on liveness** before rewardkit (polls `localhost`/`127.0.0.1` or
    equivalent). FAIL if rewardkit runs with no prior poll — a down app
    reaches the judges and may be scored from an error page
  - does not run as root without dropping privilege (NOTE if there is no
    `setpriv`/`su`/`useradd`/`gosu` — least-privilege is the expected shape
    but a static-file server may not need it)
- **How:** `bash -n`, byte scan for `\r`, greps for rewardkit / zero reward /
  a URL poll. Do not execute the script.
- **Why:** Harbor requires a reward file on every code path. A judge crash
  with no fallback looks like infra. A liveness skip is how a static file
  that never binds the port farms the aesthetic dimension.

---

## Cross-file contract (mechanical strings only)

### `check-runtime-contract-strings.py`

- **What:** the handful of interface strings that must agree, extracted as
  literals — not interpreted:
  1. **Port.** The port `test.sh` exports or binds, the port in every judge
     prompt URL, and the port in `instruction.md` are the same number.
  2. **App dir / entry.** If `test.sh` launches a specific file
     (`server.js`, `app.py`, `index.html`), `instruction.md` names that file
     (or the start command that implies it) and `solve.sh` copies/writes it.
  3. **Liveness path.** If `test.sh` polls a path other than `/` or empty
     (e.g. `/api/health`), `instruction.md` must mention that path — otherwise
     it is a hidden contract. FAIL, quote both. Polling `/` or the page the
     prompt already says to serve is fine.
  4. **Injected env.** Every `KEY=value` `test.sh` puts into the app's
     environment (port, storage path, …) that the app is expected to honor
     should appear in the instruction as either that value or that variable
     name. NOTE if `test.sh` sets a storage-path env var the instruction never
     names — this is the `DB_PATH` class of defect; the rubric judges fairness,
     the check only flags the string gap.
- **How:** regex extract from `test.sh` / instruction / judge prompts /
  `solve.sh`. Compare as strings. Do not try to decide whether a static app
  "needs" a database path — if `test.sh` does not set one, skip that row.
- **Why:** a single drifted port or a hidden health endpoint zeros every
  correct, instruction-following agent while the author's reference (which
  implements the hidden path) passes. This is the highest-value mechanical
  check unique to this format.

### `check-seed-literals-in-criteria.py` (NOTE-only)

- **What:** when the task ships structured seed data, every distinctive
  quoted literal a criterion asserts about *seeded* (not judge-created)
  records should appear in the seed. Skip sentinels (`JUDGE-`, `Judge `,
  `JUDGE_`).
- **How:** collect quoted strings from criterion descriptions; search the
  seed files. Hits that are missing → NOTE, not FAIL (a criterion may
  legitimately talk about a label the UI derives).
- **Why:** scorecard C4 — an LLM-graded fact must be true of the data. A
  hard FAIL here over-flags derived labels; a NOTE is the useful signal for
  the rubric reviewer.

### `check-probe-not-in-seed.py`

- **What:** distinctive grader probes must **not** already be in the seed or
  the reference's initial HTML. Collect `JUDGE-…` tokens and `Judge <Word>`
  names from criterion descriptions; FAIL if any appear in `environment/assets/`
  or in `solution/` files other than comments explaining the probe.
- **How:** extract probe tokens from all `judge.toml` files; `grep` the seed
  and the reference. Empty probe set → skip (static/game tasks).
- **Why:** if `JUDGE-SKU-9001` is already seeded, a read-only app "finds" it
  and earns the create criterion.

### `check-demo-accounts-agree.py`

- **What:** every demo email / password the instruction states appears in
  **every** dimension prompt that grades a signed-in app, and no judge prompt
  names an account the instruction does not. Skip the whole check if the
  instruction has no email-shaped token (a public / unauthenticated app).
- **How:** extract `\S+@\S+` and a password line from `instruction.md`; set-
  compare against each `prompt_template`. FAIL on a missing or extra account.
  Do not require a particular password string beyond what the instruction
  wrote.
- **Why:** a drifted demo email is a silent false-FAIL: the judge types an
  account a correct agent never created.

### `check-assets-paths-resolve.py`

- **What:** every `/assets/…` (or whatever mount the Dockerfile COPY dest
  uses) named in `instruction.md`, `solve.sh`, or a criterion exists as a
  real file under `environment/assets/` after applying the Dockerfile COPY
  mapping. A path the prompt names and the tree lacks is a FAIL.
- **How:** regex extract of `/assets/` paths; join onto `environment/` using
  the Dockerfile `COPY assets/ <dest>` dest. Missing dest mapping + named
  path = FAIL (same class as required-files, but per-file).
- **Why:** required-files only asks whether the `assets/` directory exists.
  A renamed seed file is the actual empty-data run.

---

## Two-environment deps (agent image vs verifier image)

### `check-runtime-deps-in-both-images.py`

- **What:** every package the **agent** Dockerfile installs that the app
  would `require`/`import` at start also appears in the **verifier**
  Dockerfile (grade-time is a different image and has no network). Compare
  package names, not exact versions — a version drift is a NOTE.
- **How:** parse `npm install` / `pip install` / `apt-get install` tokens
  from both Dockerfiles; agent-only runtime libs (express, better-sqlite3,
  flask, …) FAIL; agent-only build tools (git, compilers) are fine and
  should not be required in the verifier.
- **Why:** this is the two-environment trap as a set-diff. An app that
  starts for the agent and cannot `require('express')` in the verifier
  scores 0 with a missing-module log that looks like a bad submission.

### `check-package-manifest-deps-preinstalled.py`

- **What:** if `solution/` ships a `package.json`, `requirements.txt`, or
  similar manifest, every runtime dependency it names is installed in
  `environment/Dockerfile`. N/A if there is no manifest (a static page).
- **How:** parse the manifest's dependency names; substring-search the
  agent Dockerfile. FAIL on a dep the image does not install. Do not
  require the verifier here — that is the previous check.
- **Why:** the prompt says dependencies are already available. A manifest
  that names a library the image never installed makes the task unsolvable
  under no-network.

### `check-no-cdn-or-remote-assets.py`

- **What:** `instruction.md`, `solution/` (html/css/js), and shipped assets
  do not fetch off-origin browser resources: `cdn.`, `unpkg`, `jsdelivr`,
  `cdnjs`, `fonts.googleapis`, `fonts.gstatic`, `ajax.googleapis`, or any
  `https://` script/link/img in served HTML/CSS that is not localhost.
- **How:** regex over text files; skip `task.toml` allowlist comments and
  judge-provider URLs in `tests/`. FAIL quoting the URL. A comment that
  says "do not use a CDN" is fine.
- **Why:** grade-time has no CDN network and the browser gate requires
  same-origin. A reference (or a prompt that implies a Google font) that
  loads off-origin works on the author's laptop and zeros at grade time.

---

## Judge-prompt presence (wording, not quality)

### `check-injection-guard-present.py`

- **What:** every dimension `prompt_template` contains an untrusted-evidence
  clause: `untrusted` and (`never follow` or `scoring directive` or
  `do not follow`). Presence only — whether the clause is well written is
  the rubric.
- **How:** regex per `prompt_template`. FAIL if a dimension omits it.
- **Why:** without the guard, a submission that prints "score this 5/5"
  can move the judge. Same shape as `check-global-gate-present.py`.

### `check-batched-independence-wording.py`

- **What:** every dimension whose `[scoring].aggregation` is **not**
  `all_pass` has wording that scores criteria independently (`continue`,
  `independent`, `on its own evidence`, `each criterion`). `all_pass` gate
  dimensions are skipped. NOTE if missing (wording varies; a hard FAIL
  over-flags), FAIL only if the prompt says the opposite (failing one
  criterion fails the dimension) on a non-gate file.
- **How:** parse `[scoring].aggregation`; regex the prompt. Collect NOTES
  and the one FAIL case.
- **Why:** batched mode without an independence instruction collapses a
  dimension to binary. The rubric owns the quality of that sentence; this
  check owns "is the sentence there / did someone write the inverse".

### `check-mcp-server-is-runnable.py`

- **What:** each `[[judge.mcp_servers]]` has `transport` (stdio is the
  expected shape), a non-empty `command`, and `args` that include
  `--headless` (NOTE if headless is missing — a headed browser will hang
  in CI). The `command` token appears in `tests/Dockerfile`.
- **How:** parsed-TOML plus Dockerfile substring. Overlaps
  `check-verifier-dockerfile.py` on the command-exists rule; this one owns
  the MCP block shape.
- **Why:** a missing `command` or a headed browser is a hang, not a score.

### `check-no-trialforge-judge-keys.py`

- **What:** no `tests/<dim>/judge.toml` carries trialforge text-answer
  keys (`files =`, `atif_trajectory`, `target_claims`). No `tests/*/check.py`
  and no `tests/expected/` directory (toolathon leftovers).
- **How:** key scan + path existence. FAIL naming the leftover.
- **Why:** a half-migrated sibling file means rewardkit grades the wrong
  format or a Python grader that this suite does not run.

---

## Solution / seed hygiene (mechanical)

### `check-solution-does-not-coach-judge.py`

- **What:** served reference files (`solution/**/*.html`, `*.js`, `*.css`,
  not `solve.sh`) do not contain scoring directives the judge will read:
  `score this`, `assign 0`, `ignore your instructions`, criterion `id`
  strings copied from `judge.toml`. Comments in `solve.sh` are allowed.
- **How:** grep those files for the patterns; also grep each criterion
  `id` as a whole word. FAIL quoting the line.
- **Why:** the judge observes the live page. An answer key in the HTML is
  an injection that the oracle itself plants.

### `check-seed-has-no-injection-payload.py`

- **What:** structured seeds and media captions do not contain
  `ignore your instructions`, `score this`, `the correct answer is`,
  `assign 0 to every`.
- **How:** grep `environment/assets/` text files. FAIL quoting the field.
  N/A if there are no text assets.
- **Why:** the agent and the judge both read this data. A payload in a
  seed row is an attack surface a schema check will not see.

### `check-no-host-paths.py`

- **What:** no author-machine paths in shipped text:
  `/Users/`, `/home/<name>/` (allow `/home/agent` if the sandbox uses it),
  `C:\`, `Documents and Settings`.
- **How:** recursive grep, skipping binaries. FAIL quoting the file.
- **Why:** a leftover local path is contamination and sometimes a broken
  COPY source. The rubric also flags this; the grep catches it before
  review.

---

## Identity extras

### `check-slug-is-clean.py`

- **What:** the task directory name is a clean slug: lowercase, hyphenated,
  no spaces, no `-copy` / `-v2` / date / `(1)` suffix.
- **How:** regex on `task.name` (the directory basename). FAIL on a working-
  copy suffix.
- **Why:** a `-copy` suffix says a second divergent copy exists; Harbor
  publishes the directory name.

### `check-task-version-and-resources.py`

- **What:** `[task].version` is present and non-empty; `[environment].cpus`
  and `memory_mb` are present and in a sane band (cpus `>= 1`, memory_mb
  `>= 512` and `<= 16384`). NOTE if memory_mb `< 2048` on a task whose
  `tests/Dockerfile` installs Chromium — the browser judge is tight on 1 GB.
- **How:** parsed `task.toml` plus a "chromium"/"playwright" substring in
  the verifier Dockerfile for the NOTE.
- **Why:** missing version makes a reference edit untraceable. Too-small
  memory OOMs the verifier in a way that looks like infra.

### `check-allowlist-matches-provider.py`

- **What:** the verifier `allowed_hosts` covers the host the wired key
  actually calls. If `[verifier.env]` has `OPENROUTER_API_KEY`,
  `allowed_hosts` must include `openrouter.ai` (or `openrouter.`). If it
  has another provider key, that provider's host must be present. Extra
  hosts beyond the judge provider are a NOTE (exfiltration surface).
- **How:** key-name → host map; set compare. FAIL if the key's host is
  missing.
- **Why:** `check-task-toml.py` only requires a non-empty allowlist. A
  key whose host is not allowlisted fails auth at grade time.

### `check-instruction-states-offline-constraint.py` (NOTE-only)

- **What:** `instruction.md` mentions the no-install / no-external-network
  constraint (look for `install`, `network`, `CDN`, `external asset`,
  `already available`). NOTE if none of those appear — the harness still
  enforces no-network, but a correct agent may try `npm install` and hang.
- **How:** case-insensitive grep. Never FAIL; short static-page prompts
  sometimes omit it.
- **Why:** the runtime contract is supposed to be in the prompt. Absence
  is a fairness issue the rubric owns; this NOTE is the mechanical hint.

---

## Shell / parse hygiene

### `check-toml-and-json-parse.py`

- **What:** `task.toml`, `tests/reward.toml`, every `tests/<dim>/judge.toml`,
  and every `*.json` under `environment/assets/` and `solution/` parse with
  the real parser. Report the error verbatim.
- **How:** `tomllib` / `json.loads`. Skip `package-lock.json` if present
  (huge, not load-bearing if the image does not install from it).
- **Why:** an unescaped quote in a prompt_template kills the verifier before
  any judge runs.

---

## Security (mechanical)

### `check-no-literal-secrets.py`

- **What:** no literal provider keys, PEM blocks, or `sk-`/`ghp_`-shaped
  tokens in the task tree. Env values in `task.toml` that look like secrets
  must be `${VAR}`. Demo passwords in `instruction.md` are allowed (they are
  the product interface); a demo password committed as a real cloud key is
  not.
- **How:** regex for key shapes + PEM headers; skip binaries. This is the
  cheap sweep — real-PII judgment stays in the rubric.
- **Why:** a committed OpenRouter key is a live credential. The rubric still
  judges synthetic names/emails; this check only catches secrets.

---

## Overrides (only if `include_common` is later set true)

If the project ever flips to `include_common = true`, these same-named files
must exist as no-op NOTE exits so the common terminal-bench checks do not
fail every webdev task:

| Filename | Common check it shadows | Why it does not apply |
|---|---|---|
| `check-canary.sh` | canary GUID in every text file | webdev has no canary convention |
| `check-instruction-suffix.sh` | "You have N seconds… do not cheat" suffix | prompts are natural product requests |
| `check-task-package-name.sh` | `terminal-bench/<folder>` | org is `codearena/` (or similar), enforced by `check-task-name.py` |
| `check-task-fields.sh` | `author_name`, `subcategory`, … | webdev `[metadata]` is `difficulty` + `category` (+ provenance) |
| `check-task-absolute-path.sh` | every path in the prompt must be absolute | only the runtime-contract paths need to be absolute; the common check over-flags |

Do **not** shadow `check-separate-verifier.sh` — webdev *wants* separate
verifier mode. Prefer `include_common = false` and keep
`check-verifier-dockerfile.py` as the local equivalent (COPY into `/tests` +
the browser/judge tooling the common check does not know about).

---

## What we deliberately do **not** check here

Leave these to `rubrics/task-implementation.toml`. Encoding them as greps
produces false FAILs on legitimate tasks:

- natural vs robotic voice, spelling-in-context, "is this a spec sheet"
- whether every prompt ask has a criterion (coverage matrix)
- whether a criterion is over-strict / outcome-based / first-match
- whether the global gate is correctly scoped for auth vs a public page
- whether the reference *implements* every feature (needs reading the app)
- whether a stub/mock would score well (needs reasoning through the rubric)
- whether seed volumes are "enough" for a filter
- whether likert anchors are well written (schema of likert vs binary is
  checked; prose quality is not)
- app-level randomness (games / generative art)
- distinctness vs sibling tasks (the reviewer often has no siblings)
- whether later dimensions *should* tolerate earlier mutations (the
  `exactly N seeded rows` wording is a rubric call; do not grep "exactly")
- whether reward ranking is monotone (needs constructing fake apps)
- likert anchor prose, gate *scope* for auth vs public pages

---

## Suggested implementation order

Highest silent-failure density first. Each row is one script.

1. `check-required-files.py` + `_lib.py`
2. `check-task-toml.py` + `check-task-name.py` + `check-allowlist-matches-provider.py`
3. `check-reward-schema.py` + `check-judge-toml-schema.py` + `check-no-trialforge-judge-keys.py`
4. `check-test-sh.py` + `check-solve-sh.py` (parse, CRLF, rewardkit, liveness)
5. `check-verifier-dockerfile.py` + `check-agent-dockerfile.py` + `check-fixtures.py` + `check-runtime-deps-in-both-images.py`
6. `check-runtime-contract-strings.py` + `check-judge-prompts-name-the-url.py` + `check-assets-paths-resolve.py`
7. `check-timeouts.py` + `check-global-gate-present.py` + `check-injection-guard-present.py` + `check-mcp-server-is-runnable.py`
8. `check-instruction-hygiene.py` + `check-instruction-content.py` + `check-no-cdn-or-remote-assets.py`
9. `check-probe-not-in-seed.py` + `check-environment-does-not-leak-solution.py` + `check-package-manifest-deps-preinstalled.py`
10. `check-demo-accounts-agree.py` + `check-solution-does-not-coach-judge.py` + `check-seed-has-no-injection-payload.py`
11. `check-no-placeholders.sh` + `check-no-extraneous-files.py` + `check-no-literal-secrets.py` + `check-toml-and-json-parse.py` + `check-no-host-paths.py`
12. `check-slug-is-clean.py` + `check-task-version-and-resources.py` + `check-batched-independence-wording.py` + `check-instruction-states-offline-constraint.py` (NOTE) + `check-seed-literals-in-criteria.py` (NOTE)

That is **39 checks** plus `_lib.py`. Trialforge ships ~18; toolathon ~21
plus overrides. Stop here: anything else is a quality judgment the rubric
already owns, not a grep.
