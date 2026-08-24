# Toolathon deterministic checks

Every file here is a standalone check script, invoked by the autoreviewer as
`<check> <task-dir>` with the project root as the working directory
(`core/deterministic.py`). Contract:

- **exit 0 = pass**, non-zero = fail
- print `FAIL <path>: <reason>` for each failure, `NOTE ...` for advisory
  findings that should not block
- collect every failure before exiting; never fail-fast on the first

Because `project.toml` sets `include_common = true`, each task is also checked
against the repo-root `checks/` common set. A check here whose **filename
matches** a common check shadows it — that is how the [Overrides](#overrides)
section below retires common checks written for terminal-bench conventions that
do not apply to toolathon.

`_lib.py` is the shared helper module (task discovery, TOML loading, the
`extra_references/tool-list.json` inventory, uniform reporting). It is not a
check; running it directly exits 0 as a no-op.

---

## Layout & scaffolding

### `check-required-files.py`
- **What:** the required task layout exists: `instruction.md`, `task.toml`,
  `tests/reward.toml`, `tests/test.sh`, `solution/solve.sh`,
  `environment/Dockerfile`, `environment/runtime/setup.sh`, `tests/expected/`.
  `README.md` is a NOTE-level recommendation only.
- **How:** plain path-existence checks against the task directory.
- **Why:** every later check assumes this skeleton; a missing file here fails
  downstream in ways that are harder to read than a direct "file missing".

### `check-no-placeholders.sh`
- **What:** no `CHANGE-ME` marker anywhere in the task.
- **How:** recursive `grep -nI` over all files, skipping binary fixtures
  (`*.bundle`, `*.db`, `*.sqlite`, `*.xlsx`) so a binary blob containing those
  bytes cannot false-fire.
- **Why:** a task still carrying template scaffolding was copied from a
  template and never finished; the grader would happily score placeholder text.

---

## Instruction quality

### `check-instruction-content.py`
- **What:** `instruction.md` is finished prose: no `TODO`/`FIXME` markers, and
  at least `INSTRUCTION_MIN_WORDS` (default 30) words; 30–50 words is a NOTE.
- **How:** regex for draft markers with line numbers; word count against the
  floor. 30 was chosen so the shortest real instruction in the suite
  (doa-routing, 37 words) passes while a stub still fails.
- **Why:** placeholder scans catch *unfinished scaffolding*; this catches an
  *unfinished prompt* — a stub that is technically placeholder-free but carries
  too little for the persona to act on.

### `check-instruction-hygiene.py`
- **What:** the instruction reads as a natural persona request: it names no
  tool IDs (bare or `{server}_`-prefixed), no unambiguous MCP server names
  (`gw`, `filesystem`, `pptx`, `terminal`), no env keys (`MCP_SERVERS`,
  `LOCAL_TOOLS`, `GATEWAY_PORT`, `TASK_ID`), and no grader machinery
  (`rewardkit`, `judge`, `criterion`, `reward.toml`, `check.py`, …).
- **How:** word-boundary regex over the instruction, with the banned tool/server
  lists built from `extra_references/tool-list.json`. Server names that are
  common English words (`time`, `memory`, `word`, `excel`) are deliberately
  *not* banned as bare words — their tools are still caught by the
  `{server}_`-prefixed form.
- **Why:** the persona must work out the toolchain itself; naming tools or the
  grader breaks the fourth wall and leaks the rig into the task.

### `check-instruction-spec-leak.py` (NOTE-only)
- **What:** the prompt states the goal, not the specification. Two proxies:
  length over ~120 words, and rule-speak in the prompt (`ROUND_HALF_UP`,
  "standard deviation", "strictly greater than", "decimal arithmetic", …).
- **How:** word count plus a pattern list; both emit NOTEs, never FAILs.
- **Why:** human calibration of segment-growth (2026-08-19) found the prompt
  pre-disclosing every trap the Methodology sheet was built to test — with the
  spec in the prompt, the task measures instruction-following instead of
  spec-reading. Heuristic, so advisory; the semantic judgment stays with the
  rubric review.

---

## Oracle / solution

### `check-solve-output.py`
- **What:** `solution/solve.sh` actually emits an answer: non-trivial content
  beyond the shebang/`set -euo pipefail`/comments, and at least one
  output-producing construct (`cat`/`tee`/`echo`/`printf`/heredoc, or a write
  to `/logs` or `/app`). A thin wrapper that delegates to a sibling script
  (e.g. doc-refiling's 7-line `solve.sh` → `solve.py`) is followed one level.
- **How:** static regex scan — it does not run the script.
- **Why:** Harbor's OracleAgent captures `solve.sh` stdout; a solve that
  computes quietly hands the grader nothing and scores the oracle ~0 however
  correct it is — a permanently red pipeline that looks like a bad task.

---

## task.toml contract

### `check-task-toml.py`
- **What:** `task.toml` is valid TOML and carries the toolathon field contract:
  `schema_version = "1.4"`, `[task].keywords` includes `tool-use`,
  `[environment.env]` carries `MCP_SERVERS`/`LOCAL_TOOLS`/`GATEWAY_PORT`,
  `[verifier.env].TASK_ID` present, secrets as `${VAR}` templates, no
  `[environment].docker_image`, and no trialforge-only metadata fields
  (`enabled_tools`, `persona`, `domain`, `target_*`).
- **How:** `tomllib` parse plus field assertions; secrets detected by
  key-name match (`key|token|secret|password`) and required to be `${VAR}`.
- **Why:** `docker_image` makes Harbor pull a prebuilt image and *silently skip
  the Dockerfile*, so fixtures never apply. Literal secrets are credentials
  committed to git. Trialforge-only fields mean the task was written against
  the wrong format.

### `check-task-name.py`
- **What:** `[task].name` is `context-mesh/<dirname>` and its last path
  component equals the task directory name.
- **How:** string comparison of the name suffix against `task.name`.
- **Why:** a mismatch means a rename that didn't propagate — the task is
  findable by directory but cross-references by name dangle.

### `check-network-mode.py`
- **What:** `[agent].network_mode` and `[verifier].network_mode` must be
  `"no-network"`; an unset key is a NOTE, `"public"` is a FAIL.
- **How:** reads the two keys from the parsed `task.toml`.
- **Why:** toolathon tasks need no egress — the agent reads local files and
  talks to the gateway over loopback, and the verifier runs deterministic
  rewardkit functions (no LLM judge). Human calibration flagged `"public"` on
  every reviewed task and asked for exactly this suite-wide sweep. Public
  networking widens the prompt-injection exfiltration surface and lets a task
  accidentally depend on live external state.

---

## Tool surface (MCP)

### `check-mcp-servers-env.py`
- **What:** `[environment.env].MCP_SERVERS` parses to a non-empty list; every
  name is a real server in `extra_references/tool-list.json`; no duplicates;
  the base servers `filesystem` + `terminal` are always present; `LOCAL_TOOLS`
  names only known local tools (`claim_done`).
- **How:** splits the comma-list and set-compares against the 7 servers in the
  committed tool inventory (`excel`, `filesystem`, `memory`, `pptx`,
  `terminal`, `time`, `word`), with did-you-mean hints on unknown names.
- **Why:** the gateway reads `MCP_SERVERS` and exposes each named server's
  tools — a typo is a **silent no-op**: the server simply never appears, the
  agent underperforms for no visible reason, and nothing in Harbor or the
  runtime says a word. This is toolathon's analogue of trialforge's
  `check-enabled-tools`.

### `check-mcp-config.py`
- **What:** exactly one `[[environment.mcp_servers]]` block, named `gw`,
  `transport = "sse"`, with a `url` and no `command` (never stdio); server
  names unique.
- **How:** structural assertions over the parsed TOML blocks.
- **Why:** toolathon exposes tools through a single SSE gateway; a stdio
  server, a second gateway, or a missing url surfaces only as a health-check
  timeout that looks like a network fault. A duplicate name silently shadows
  one entry in Harbor's server map.

---

## Grading (rewardkit)

### `check-reward-schema-toolathon.py`
- **What:** `tests/reward.toml` carries exactly the two aggregate blocks
  `[[reward]]` named `a_reward` and `reward`, both
  `aggregation = "weighted_mean"`; `[judge]`/`[[criterion]]` are rejected.
- **How:** parses the TOML and asserts names + aggregation; hard-fails on the
  trialforge judge keys.
- **Why:** toolathon grades via per-dimension `check.py` functions aggregated
  by these two blocks — identical across all 16 tasks. `[judge]`+`[[criterion]]`
  is the trialforge LLM-judge format; its presence means a half-migrated task.
  `all_pass` would collapse to 0.0 unless every dimension lands, destroying
  partial credit.

### `check-criterion-dirs.py`
- **What:** `tests/expected/` exists (the baked answer key); every other
  `tests/<dimension>/` directory contains a `check.py` that imports rewardkit;
  at least one dimension dir exists.
- **How:** directory scan plus an import regex (`from rewardkit import …` /
  `import rewardkit`) per file.
- **Why:** this is toolathon's analogue of trialforge's criterion-count check —
  it proves the scoring logic actually exists. A dimension dir without a
  `check.py`, or one that doesn't go through rewardkit's `@criterion`, leaves
  the `[[reward]]` blocks with nothing to aggregate.

### `check-test-sh-rewardkit.sh`
- **What:** `tests/test.sh` invokes rewardkit (hard FAIL if not), and writes a
  fallback `{"reward": 0.0}` on failure paths (NOTE if absent).
- **How:** grep for a rewardkit invocation and for a zero-reward write.
- **Why:** rewardkit is what discovers `reward.toml`, runs the dimension
  checks, and writes `/logs/verifier/reward.json` — without it Harbor reports
  `RewardFileNotFoundError`. And since Harbor requires a reward file on *every*
  code path, a rewardkit crash without a fallback reads as an infrastructure
  error instead of a scored 0.0.

### `check-grader-formula-fallback.py`
- **What:** any `tests/*/check.py` that reads workbook values with
  `openpyxl.load_workbook(..., data_only=True)` must also load with
  `data_only=False` (dual-load fallback), parameterize the flag
  (`data_only=cached` over `(True, False)`), or use the `formulas` library.
- **How:** AST analysis — inspects the `data_only` keyword of every real
  `load_workbook` call, so docstrings discussing the issue don't count.
  Graders that route through rewardkit helpers (no direct openpyxl) can't be
  inspected and are skipped.
- **Why:** `data_only=True` returns *cached* values; a programmatically written
  workbook has no cache, so every formula cell reads as `None`. Human
  calibration measured an otherwise-perfect formula-written answer failing
  23/32 cells — the task punishing idiomatic use of the excel tool it
  deliberately hands the agent, with a misleading `got '(blank)'` message.

### `check-grader-no-active-sheet.py`
- **What:** no grader reads the workbook's `.active` sheet.
- **How:** AST walk of each `tests/*/check.py`, flagging any attribute read
  named `active` (comments and docstrings can't false-positive).
- **Why:** an agent that leaves an empty leading `Sheet1` in front of its real
  answer is *correct* — a grader trusting `.active` grades the empty sheet.
  Calibration listed this as a latent issue on every reviewed task; this check
  is the regression guard.

---

## Environment / image

### `check-dockerfile-toolathon.py`
- **What:** `environment/Dockerfile` builds on `task-image:<tag>` (never
  `:latest`), declares the pinned Toolathlon runtime clone (`RUNTIME_REPO` +
  `RUNTIME_REF` with a full 40-hex SHA), runs `uv sync`, installs
  `harbor-rewardkit`, and `COPY`s `task/` and `runtime/` into the image.
- **How:** regex over the comment-stripped Dockerfile body. The tag itself is
  not pinned, so a tag bump is a one-line change, not a check edit.
- **Why:** these are the load-bearing invariants of the (byte-identical) image
  contract. A branch-tip `RUNTIME_REF` makes the image non-reproducible; a
  missing rewardkit install fails the grade with a missing tool.

### `check-fixtures.py`
- **What:** every relative `COPY`/`ADD` source in the Dockerfile resolves under
  `environment/`; no build-time `git clone` from a live remote except the
  pinned Toolathlon runtime (`RUNTIME_REPO`/`RUNTIME_REF`, 40-hex SHA).
- **How:** parses COPY/ADD lines (skipping JSON-array form, absolute URLs, and
  `${VAR}` sources), globs wildcards, and scans for remote clones.
- **Why:** a missing COPY source is a container build failure 20 minutes into a
  run; an unpinned clone couples the task to a live remote and breaks
  reproducibility.

### `check-healthcheck.py`
- **What:** `[environment.healthcheck]` exists with a non-empty `command`,
  positive `timeout_sec`/`interval_sec`/`retries`, and
  `start_period_sec >= 0`.
- **How:** field assertions on the parsed TOML table.
- **Why:** the healthcheck runs `runtime/setup.sh`, which writes
  `task_config.json` from `MCP_SERVERS`/`LOCAL_TOOLS` and starts the gateway —
  a malformed block is a silent boot failure that surfaces only as a
  health-check timeout.

### `check-spec-doc-present.py`
- **What:** at least one specification document (`*.md`/`*.docx`/`*.pdf`) under
  `environment/task/initial_workspace/`.
- **How:** recursive file scan by suffix.
- **Why:** toolathon's contract is that the *rules* live in a discoverable
  workspace document (policy, methodology, SOP, taxonomy) and the prompt only
  names the deliverable. Human calibration of vendor-outliers found the
  opposite — a workspace with only data files forces every rule into the
  prompt, and the task measures instruction-following instead of spec-reading.

### `check-artifacts.py`
- **What:** when the top-level `artifacts` array is present, it is a non-empty
  list of absolute `/app/…` paths, and each basename has a matching answer key
  in `tests/expected/`. Absent is a NOTE (3/16 tasks legitimately omit it).
  Output filenames named in `instruction.md` but missing from `artifacts` are
  a cross-reference NOTE.
- **How:** parses the array (string or `{source = …}` table form), compares
  basenames against the `tests/expected/` listing, and regex-matches output
  filenames in the instruction.
- **Why:** `artifacts` is what Harbor collects as deliverables; a stale entry
  after a rename means the grader's answer key and the declared deliverable
  have drifted apart. Absence is legal, so it cannot be a FAIL.

---

## Overrides

These shadow same-named repo-root common checks (`core/deterministic.py` skips
a common check whose filename matches a project check). Each exits 0 with a
NOTE explaining why the common check does not apply to toolathon.

### `check-canary.sh`
- **Overrides:** the common canary-GUID check. Toolathon has no canary
  convention; the common check would fail all 16 tasks.

### `check-separate-verifier.sh`
- **Overrides:** the common separate-verifier check (`environment_mode =
  "separate"` + a verifier Dockerfile). Toolathon grades in the shared agent
  container via rewardkit; there is no separate verifier image.

### `check-task-fields.sh`
- **Overrides:** the common terminal-bench metadata check (`author_name`,
  `subcategory`, `tags`, …). Toolathon `[metadata]` carries only `difficulty`
  + `category`; the toolathon field contract lives in `check-task-toml.py`.

### `check-instruction-suffix.sh`
- **Overrides:** the common check requiring the canonical "You have N seconds…
  do not cheat…" instruction suffix. Toolathon instructions are persona
  requests without it; instruction quality is covered by
  `check-instruction-content.py` / `check-instruction-hygiene.py` /
  `check-instruction-spec-leak.py`.

### `check-task-package-name.sh`
- **Overrides:** the common `terminal-bench/<folder>` name check. Toolathon
  publishes under the `context-mesh` org; enforced by `check-task-name.py`.

### `check-task-absolute-path.sh`
- **Overrides:** the common check requiring absolute paths in `instruction.md`.
  Toolathon's design is that the agent operates in a known workspace root and
  instructions deliberately reference files relative to it
  (`sop/Reconciliation_Procedure.docx`); the common check would fail the 7
  tasks that do so.

---

*Checks 17–21 (`grader-formula-fallback`, `network-mode`, `spec-doc-present`,
`grader-no-active-sheet`, `instruction-spec-leak`) were added from human
calibration reviews of segment-growth and vendor-outliers (2026-08-19) — they
encode defects measured by running real probes against the tasks, not just
format conventions.*
