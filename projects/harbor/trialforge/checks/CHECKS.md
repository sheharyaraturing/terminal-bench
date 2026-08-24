# TrialForge deterministic checks

Every file here is a standalone check script, invoked by the autoreviewer as
`<check> <task-dir>` with the project root as the working directory
(`core/deterministic.py`). Contract:

- **exit 0 = pass**, non-zero = fail
- print `FAIL <path>: <reason>` for each failure, `NOTE ...` for advisory
findings that should not block
- collect every failure before exiting; never fail-fast on the first

`project.toml` sets `include_common = false`: the repo-root common checks are
written for terminal-bench conventions (canary strings, instruction suffixes,
separate verifiers) that TrialForge does not follow, so only these
purpose-built checks run.

`_lib.py` is the shared helper module (task discovery, TOML loading, the tool
inventory, the suite constants — claim/tool-call/allowlist bands, judge model,
image prefix — and uniform reporting). It is not a check; running it directly
exits 0 as a no-op.

`tool_inventory.txt` is data, not a check: the committed offline copy of the
environment image's full tool surface (`POST /list-tools` on the pinned
`turing-mcpatlas` image). It lets the tool-surface checks run with no network.

---



## Layout & scaffolding



### `check-required-files.py`

- **What:** the required task layout exists: `instruction.md`, `task.toml`,
`tests/reward.toml`, `tests/test.sh`, `solution/solve.sh`. `NOTES.md` is a
NOTE-level recommendation.
- **How:** plain file-existence checks.
- **Why:** every later check assumes this skeleton. `NOTES.md` is where the
ground-truth derivation, seed spans, and oracle/nop validation commands live
— optional, but its absence is worth surfacing.



### `check-no-placeholders.sh`

- **What:** no `CHANGE-ME` marker anywhere in the task.
- **How:** recursive `grep -nI`, skipping binary fixtures (`*.bundle`, `*.db`,
`*.sqlite`) so a binary blob containing those bytes cannot false-fire.
- **Why:** a task still carrying template scaffolding was copied from TEMPLATE
and never finished — the judge would happily grade
"CHANGE-ME: states that specific fact is specific value".

---



## Instruction quality



### `check-instruction-content.py`

- **What:** `instruction.md` is finished prose: no `TODO`/`FIXME` markers, and
at least `INSTRUCTION_MIN_WORDS` (default 50) words.
- **How:** regex for draft markers with line numbers; word count against the
floor.
- **Why:** placeholder scans catch unfinished *scaffolding*; this catches an
unfinished *prompt* — a stub that is placeholder-free but too thin to be a
real persona request.



### `check-instruction-hygiene.sh`

- **What:** the instruction reads as a natural persona request: it names no
tool and no server from the inventory, leaks no grader machinery
(`reward.toml`, `rewardkit`, `enabled_tools`, `mcp_servers`, `oracle`,
`final_answer.txt`, `task.toml`, `harbor`, …), and names no sandbox paths
(`/data/…`, `/logs/…`).
- **How:** pure greps — word-boundary case-insensitive patterns for grader
terms, fixed-string matches for sandbox paths, and the tool/server names from
`tool_inventory.txt`.
- **Why:** CONTRIBUTING.md: the agent must work out the toolchain and the data
layout itself. Naming a tool, a server, or a path hands over what the task is
built to test; naming the grader breaks the fourth wall.

---



## Oracle / solution



### `check-solve-output.py`

- **What:** `solution/solve.sh` emits an answer the judge can see: non-trivial
content beyond the shebang/`set -euo pipefail`/comments, and at least one
output-producing construct (`cat`/`tee`/`echo`/`printf`/heredoc, or a direct
write to `/logs/agent/final_answer.txt` / `oracle.txt`).
- **How:** static regex scan — it does not run the script.
- **Why:** Harbor's OracleAgent captures `solve.sh` stdout into
`/logs/agent/oracle.txt`, and `test.sh` bridges that to the path the judge
reads. A solve that computes quietly scores the oracle ~0 however correct it
is. (`check-oracle-not-parrot` covers the orthogonal "is the answer *real*"
question.)



### `check-oracle-not-parrot.py`

- **What:** the oracle is a real answer, not a restatement of the claim
strings. Flags when `solve.sh` shares ≥ 60% of a claim's content words
(stop-word-filtered, claims shorter than 4 content words ignored).
- **How:** tokenizes `solve.sh` and each `[[criterion]]` description from
`tests/reward.toml`, then computes per-claim word-overlap against the
threshold.
- **Why:** a solve.sh that parrots the criterion descriptions passes the judge
while proving nothing about whether the task is solvable from the
environment. The oracle is the acceptance gate — it has to be earned.

---



## task.toml & metadata



### `check-task-toml.py`

- **What:** `task.toml` is valid TOML; `[environment].docker_image` is absent;
every `[verifier/agent/solution].env` value is a `${VAR}` template; and
`OPENROUTER_API_KEY` is wired through for the verifier.
- **How:** `tomllib` parse; `${VAR}` fullmatch on env values.
- **Why:** setting `docker_image` makes Harbor pull a prebuilt image and
*silently skip* `environment/Dockerfile`, so fixtures never apply. A literal
env value is a credential committed to git. And the rewardkit judge routes
through OpenRouter via litellm — without the key entry the judge call fails
auth at trial time.



### `check-task-name.py`

- **What:** `[task].name`'s last path component equals the task directory name.
- **How:** string comparison of the name suffix against `task.name`.
- **Why:** a mismatch means a rename that didn't propagate — the task is
findable by directory but cross-references by name dangle.



### `check-metadata-bounds.py`

- **What:** `[metadata]` carries a non-empty `persona`, a `domain` in the known
set (`software-engineering`, `research-science`), `target_tool_calls` in the
40–70 long-horizon band, and `target_claims` in the 8–15 band.
- **How:** field assertions against the suite constants in `_lib.py` (all
tunable via env vars).
- **Why:** these fields drive the suite's distribution reporting and the
quality bar. This check owns only the *absolute* ranges — the *relative*
contract (target_claims == criterion count) belongs to
`check-claims-consistency`, so the two complement rather than duplicate.

---



## Tool surface (MCP)



### `check-enabled-tools.py`

- **What:** `[metadata].enabled_tools` exists, is a non-empty string array, and
every entry appears in `tool_inventory.txt` — with did-you-mean hints that
point at the double-prefix trap (`filesystem_filesystem_read_file`).
- **How:** set membership against the committed inventory.
- **Why:** the harness filters client-side
(`tools.filter(t => enabledTools.includes(t.name))`), so a misspelled name is
a *silent* set intersection — the tool never reaches the model, the agent
underperforms for no visible reason, and nothing in Harbor, the harness, or
the sandbox says a word. Without the list at all, the agent is handed the
entire ~210-tool surface.



### `check-allowlist-budget.py`

- **What:** `enabled_tools` exposes 18–30 tools (`MIN_EXPOSED`–`MAX_EXPOSED`).
- **How:** length check against the `_lib.py` band.
- **Why:** docs/TOOL_ALLOWLISTS.md: MCP-Atlas exposes ~15 tools/task; TrialForge
holds 18–30 so the distractor ratio stays near the benchmark's while covering
40–70 calls. Too few and tool selection is trivial; too many and the surface
is noise, not signal.



### `check-no-dangerous-tools.py`

- **What:** `sqlite_delete_records` is never exposed, and no server contributes
its *entire* tool set (>2 tools) to the allowlist.
- **How:** a banned-set membership test, plus per-server exposed-vs-total
counts computed from the inventory.
- **Why:** `sqlite_delete_records` can destroy the ground truth mid-rollout and
make a bad rollout unrepeatable. A dumped full server is noise, not a
distractor.



### `check-mcp-config.py`

- **What:** each `[[environment.mcp_servers]]` block has `name` + `transport`
and either `command` (stdio) or `url` (sse/http); server names are unique;
no duplicate `enabled_tools` entries; every enabled tool's server is
declared; every declared server has at least one enabled tool.
- **How:** structural TOML assertions, then a set cross-reference between the
tool prefixes and the declared server names.
- **Why:** Harbor does not gate tools — whatever a declared server advertises,
the agent sees, and the harness filters after. An enabled tool on an
*undeclared* server never reaches the model (silent no-op); a declared server
with *zero* enabled tools burns memory and boot time for nothing; a duplicate
server name silently shadows one entry in Harbor's server map.



### `check-mcp-uvx-pin.sh`

- **What:** every `uvx` MCP server pins `mcp<2` *and* a package version
(`==` or `--from …==`); every `npx` server pins `@version`.
- **How:** line-oriented awk scan of the `[[environment.mcp_servers]]` blocks
(the structure is flat enough that awk beats a parser); failures collected
via a temp file because the block loop runs in a pipeline subshell.
- **Why:** mcp 2.0.0 is a breaking release of the Python SDK — pinning only the
server version lets the transitive SDK float to 2.0.0, the server crashes on
import, and then *silently fails to register*. An unpinned npx package floats
the same way.

---



## Grading (rewardkit judge)



### `check-reward-schema.py`

- **What:** `tests/reward.toml` satisfies the judge contract: `[judge]` present
with the model under the `judge` key (not `model` — dead config for an LLM
judge), `openrouter/`-prefixed (so litellm reads `OPENROUTER_API_KEY`),
`mode = "individual"`, non-empty `files` all under `/logs/`, no
`trajectory.json` in `files`, and `/logs/agent/final_answer.txt` included.
Plus 8–15 `[[criterion]]` blocks, each with a non-empty description,
`type = "likert"`, `points = 3`, positive `weight`; and
`[scoring].aggregation = "weighted_mean"`.
- **How:** parsed-TOML assertions over every field above; the judge model
itself is NOTE-level (only the prefix is load-bearing).
- **Why:** each rule encodes a measured silent failure. Without `[judge]` the
file is ignored and the task has no reward at all. `mode = "batched"` grades
the claims as one blob and destroys partial credit. With no `files` the judge
grades on the system prompt alone. A trajectory blows rewardkit's 1 MB file
cap and the judge receives "[skipped: file too large]". Omitting
`type`/`points` silently means binary/5, not the benchmark's likert/3.
`all_pass` collapses to 0.0 unless every claim lands — no gradient for the
policy to learn from.



### `check-claims-consistency.py`

- **What:** `[metadata].target_claims` **exactly equals** the `[[criterion]]`
count in `tests/reward.toml`.
- **How:** integer comparison across the two files.
- **Why:** the template documents the contract as exact equality — the metadata
declares the intended claim count and the reward file carries one criterion
per claim; drift between them means one was edited without the other. (An
earlier revision also asserted one `echo` per claim in solve.sh; that model
was wrong — the judge grades the answer *text*, not shell echoes — and was
removed.)



### `check-test-sh-rewardkit.sh`

- **What:** `tests/test.sh` invokes rewardkit (hard FAIL if not), and writes a
fallback `{"reward": 0.0}` on failure paths (NOTE if absent).
- **How:** grep for a rewardkit invocation and for a zero-reward write.
- **Why:** rewardkit discovers `reward.toml`, calls the judge, and writes
`/logs/verifier/reward.json` — without it Harbor reports
`RewardFileNotFoundError`. And Harbor requires a reward file on *every* code
path: a judge crash (missing API key, judge error) with no fallback reads as
an infrastructure error instead of a scored 0.0.



### `check-test-sh-oracle-fallback.sh`

- **What:** when `[judge].files` reads `final_answer.txt`, `tests/test.sh` must
reconcile it with `oracle.txt` (e.g. copy oracle.txt over when
final_answer.txt is missing/empty).
- **How:** grep cross-reference — only fires when reward.toml names
`final_answer.txt` and test.sh never mentions `oracle.txt`.
- **Why:** the oracle trap. Harbor's OracleAgent writes solve.sh stdout to
`/logs/agent/oracle.txt` and never creates `final_answer.txt`; if the judge
only reads `final_answer.txt`, the oracle produces no evidence and the
`-a oracle` gate can *never* pass — a permanently red pipeline that looks
like a bad task.

---



## Environment / image



### `check-dockerfile.py`

- **What:** `environment/Dockerfile` (when present — a task may run the base
image as-is) contains `ENTRYPOINT []`, builds `FROM` the pinned
`turing-mcpatlas` image prefix, and its FROM tag matches any
`[environment].docker_image` tag in task.toml.
- **How:** regex over the comment-stripped Dockerfile body, plus a tag
cross-reference against the parsed task.toml.
- **Why:** Harbor supplies its own agent process; the image's ENTRYPOINT runs
envsubst + the sandbox CMD and would fight it. Without `ENTRYPOINT []`
nothing works, and the symptom is a health-check timeout that looks like a
network fault. A tag mismatch between FROM and docker_image means one is
stale.



### `check-fixtures.py`

- **What:** git fixtures ship as real bundles in `environment/fixtures/`
(verified by the v2/v3 bundle magic bytes); every `*.bundle` a script
references is actually committed; no build-time `git clone` from a live
remote and no `--depth 1` shallow clones; Dockerfile COPY sources exist.
- **How:** binary header sniffing for bundles, reference scanning across
scripts/Dockerfile, and COPY-source existence checks.
- **Why:** CONTRIBUTING.md: a build-time clone makes the image
non-reproducible and couples the task to a live remote; `--depth 1` throws
away the history that `git_git_log` exists to read. A missing referenced
fixture is a container build failure 20 minutes into tier 2.

