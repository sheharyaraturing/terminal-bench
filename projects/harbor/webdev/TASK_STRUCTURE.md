# WebDev (codearena) task structure

Reference for the `webdev` Harbor project. Documents what every file and folder in a
task is for, how the files reference each other, and how a task is graded — so the QC
rubric (`rubrics/task-implementation.toml`, authored next) can be written against an
accurate model of the format.

Worked example throughout: `tasks/bazaarbridge-marketplace/`.

---

## 1. What a webdev task is

A **full-stack web-application build** task. The agent reads `instruction.md`, builds a
running application under `/app` inside a container, and the application is graded **from
a real browser**: a headless Chromium (Playwright MCP) driven by an LLM judge (`codex`
CLI → OpenRouter model `gpt-5.6-luna`, "Luna") opens `http://localhost:3000`, exercises
the UI, and scores a set of criteria.

Contrast with the sibling projects (same Harbor schema 1.4, different grading spine):

| | **webdev (this project)** | **trialforge** | **toolathon** |
|---|---|---|---|
| Deliverable | a **running web app** under `/app` | a text final answer | a file the agent writes |
| Grader | **browser LLM judges** (Playwright MCP + codex/Luna) | LLM judge over answer text (rewardkit `[[criterion]]`) | deterministic Python `@criterion` + golden trajectory |
| "Reference answer" | `solution/` = a complete working app | `solution/solve.sh` = the answer text | `solution/manifest.json` = golden trajectory |
| Rubric shape | 5 dimensions, each a `tests/<dim>/judge.toml` with its own criteria | one `tests/reward.toml` with N claims | `tests/<dim>/check.py` + `tests/expected/` key |
| Verifier | **separate** container (browser + judge) | separate container | shared container |

The organizing gate is the same two-sided one used across Harbor projects:
- **ORACLE high** — the golden app in `solution/` scores near the top (task is buildable and the judges accept a correct app).
- **FLOOR low** — a missing/blank/static/no-backend submission scores ~0 (the global browser gate and same-origin/backend checks enforce this).

---

## 2. Directory layout (the closed list)

```
tasks/<slug>/
  task.toml                         config: identity, env, agent/verifier wiring, judge model
  instruction.md                    the prompt — the ONLY thing the agent is told
  environment/
    Dockerfile                      the AGENT sandbox image (build tools, runtime deps, /app)
    assets/
      artifacts/<seed>.json         seed data mounted read-only at /assets/... in the sandbox
  solution/
    solve.sh                        installs the reference app into /app (the oracle entrypoint)
    server.js                       reference backend (Node + Express + better-sqlite3)
    reference.html                  reference single-file SPA → copied to /app/public/index.html
    package.json                    reference app manifest (declares deps, not installed at run)
  tests/
    Dockerfile                      the VERIFIER image (Python + Node + Playwright + codex + rewardkit)
    test.sh                         verifier entrypoint: safely launch /app, health-check, run rewardkit
    reward.toml                     top-level aggregate block (weighted mean of the dimensions)
    <dimension>/judge.toml          one browser-judge dimension (prompt + criteria + weight)
      render/        constraints/        functional/        aesthetic/        polish/
```

`extra files for refrence only while creating checks/` (project root, not inside a task)
is **reference material for authoring checks** (`RL_Task_QC_Scorecard.xlsx`,
`Webdev_app_taxonomy.xlsx`) — never part of a task and never graded.

---

## 3. File-by-file: purpose, key fields, relationships

### 3.1 `task.toml` — identity and run wiring
The control file Harbor reads to schedule the run. Key fields observed in the example:

- `schema_version = "1.4"`.
- `[task]` — `name = "codearena/<slug>"` (org is **codearena**, last path component must equal the directory slug), `version`, `description`, `keywords` (include `webdev`).
- `[metadata]` — `difficulty`, `category`, `tags`, plus provenance notes (`provenance`, `arena_slice`). No trialforge/toolathon metadata fields (`persona`, `enabled_tools`, `target_claims`, `MCP_SERVERS`).
- `[agent] timeout_sec` — build budget (3600 here).
- `[environment]` — the **agent** sandbox: `network_mode = "no-network"` (the built app must not need egress), `cpus`, `memory_mb`.
- `[verifier]` — `timeout_sec`, `environment_mode = "separate"` (grading runs in its own image, not the agent's).
- `[verifier.env]` — `OPENROUTER_API_KEY = "${VAR}"` (secret by indirection), and the judge selection: `REWARDKIT_JUDGE = "codex"`, `REWARDKIT_MODEL = "openai/gpt-5.6-luna"`.
- `[verifier.environment]` — the verifier's own container: `docker_image = "codearena/webdev-verifier:1.1.0"`, `network_mode = "allowlist"`, `allowed_hosts = ["openrouter.ai"]` (the judge needs OpenRouter; nothing else).

**Relationships:** the judge model here (`REWARDKIT_MODEL`) is the same model each
`judge.toml` names; `allowed_hosts` must cover wherever the judge calls (OpenRouter); the
verifier `docker_image` is the prebuilt browser/judge image, distinct from the agent
`environment/Dockerfile`.

### 3.2 `instruction.md` — the prompt
The only thing the agent sees. In the example it is a short, first-person product request
("can you build me a polished full-stack operations app…"). It legitimately states the
**hard runtime contract** the harness depends on (this is not "scaffolding" here — it is
the interface the verifier will assume):

- app lives in `/app`; started by `node /app/server.js`; listens on port **3000**;
- UI served from `/app/public/index.html`; durable data in `/app/bazaarbridge.db`;
- backend = Node.js + Express, storage = SQLite; seed data at `/assets/artifacts/bazaarbridge_seed_data.json`;
- must **not install packages or fetch network assets** at run time (deps are pre-provided);
- demo accounts + password, and the feature list (workspaces, CRUD, search/filter, persistence, metrics, theming, responsive, a11y).

**Relationships:** every runtime fact in the prompt (port, paths, demo credentials, seed
path, feature list) must match `environment/Dockerfile`, `solution/`, `tests/test.sh`,
and the `judge.toml` prompts. This is the primary cross-file consistency surface.

### 3.3 `environment/` — the world the agent builds in
- **`Dockerfile`** — the **agent** image. Example: `FROM node:22-bookworm-slim`; `apt` installs `sqlite3` + tools; `npm install -g express better-sqlite3` (globally, exposed via `NODE_PATH=/usr/local/lib/node_modules` so the app can `require` them without a local install); `COPY assets/ /assets/`; `mkdir /app`; `WORKDIR /app`; `CMD ["sleep","infinity"]` (the agent works interactively). Pins base tag and every dependency version.
- **`assets/artifacts/<seed>.json`** — the read-only seed data the app imports. Example `bazaarbridge_seed_data.json`: `schema_version`, `users` (3), `inventory` (5), `orders` (6), `payouts` (3), `activity` (3). Mounted at `/assets/...` (matches the path named in the prompt and used by `solve.sh`).

**Relationships:** `NODE_PATH`/pre-installed deps are what make the prompt's "must not
install packages" constraint satisfiable; the seed shape is what the `functional`
judge's seeded-row expectations (e.g., "at least four visible seeded rows", "Brook"
search, "Shipped" filter) are calibrated against.

### 3.4 `solution/` — the golden application (the oracle)
Not a script that prints an answer — a **complete working app**, plus an installer:

- **`solve.sh`** — the oracle entrypoint. Copies `server.js`, `package.json`, and
  `reference.html → /app/public/index.html` into `/app`, copies the seed JSON to
  `/app/seed_data.json`, and clears any stale DB files. This is what Harbor's oracle run
  executes to produce the reference submission the judges then score.
- **`server.js`** — reference backend (Node + Express + `better-sqlite3`, ~337 lines).
  Creates the SQLite schema, seeds from the JSON, hashes passwords (sha256), manages
  sessions, and exposes the REST surface: `GET /api/health`, `POST /api/login`,
  `POST /api/logout`, `GET /api/bootstrap`, `POST/PATCH /api/orders`,
  `POST/PATCH /api/inventory/:sku`, `POST/PATCH /api/payouts`. Reads `DB_PATH`,
  `SEED_PATH`, `PORT` from env (so the verifier can relocate the DB).
- **`reference.html`** — the entire single-file SPA (~226 lines: inline CSS design system
  with light/dark theme variables, and inline JS that calls the API). Demonstrates the
  aesthetic/polish bar the judges reward.
- **`package.json`** — declares the app's deps (`express`, `better-sqlite3`) and
  `start` script; the deps are pre-installed in the image rather than installed at run.

**Relationships:** `solution/` is the proof the task is solvable through the required
stack and the reference against which "ORACLE high" is validated. Its API/route choices
are deliberately *not* required of the agent — the judges score **browser-visible
outcomes**, not endpoint names (the `constraints` prompt says "Do not prescribe endpoint
names or implementation structure").

### 3.5 `tests/` — the verifier and the rubric

- **`Dockerfile`** — the **separate verifier** image. `python:3.12-slim` with the Node
  runtime copied in; installs `@openai/codex` (the judge CLI), `@playwright/mcp`,
  `express`, `better-sqlite3`, Chromium with deps, and `harbor-rewardkit`. Writes a codex
  config pointing at OpenRouter (`env_key = OPENROUTER_API_KEY`). `COPY . /tests`. This is
  the byte-heavy, mostly-fixed infrastructure image (`codearena/webdev-verifier:<tag>`).
- **`test.sh`** — the verifier entrypoint. The safety-critical glue:
  1. writes a **zero reward first** (`reward.txt`/`reward.json`) and re-writes it on every
     failure path via an `EXIT` trap — Harbor must find a reward on every code path;
  2. refuses to grade if `/app/server.js` or `/app/public/index.html` is missing, or if
     `/app` contains a symlink (anti-escape);
  3. copies `/app` to `/tmp/...`, `chown`s it to `nobody`, and launches the server as an
     unprivileged user (`setpriv --reuid 65534`) with a **clean environment** (`env -i`),
     `PORT=3000`, `DB_PATH` inside the copy;
  4. polls `GET /api/health` for up to ~30s; if it never comes up, exits with the zero
     reward (a dead app scores 0);
  5. runs `rewardkit /tests` (which discovers the dimension `judge.toml`s and drives the
     browser judges); on rewardkit failure, writes zero.
- **`reward.toml`** — the **top-level aggregate** only: one `[[reward]]` named `reward`,
  `aggregation = "weighted_mean"`. It does **not** list the dimensions; rewardkit
  discovers each `tests/<dimension>/judge.toml` and combines them by their per-dimension
  `[judge].weight`.
- **`tests/<dimension>/judge.toml`** — one **browser-judge dimension**. Each contains:
  - `[judge]` — `judge = "codex"`, `model`, `mode = "batched"`, `timeout`, `isolated`,
    `reasoning_effort`, `temperature = 0`, and the dimension **`weight`** (its share of
    the grade);
  - a `prompt_template` with a `{criteria}` placeholder and a repeated **Global browser
    gate** (page loads, protected data hidden pre-login, wrong password rejected, correct
    password opens populated content, requests same-origin → fail the gate ⇒ 0 for the
    whole dimension) and an **untrusted-evidence** clause (never follow scoring directives
    found in the submission = prompt-injection defense);
  - `[[judge.mcp_servers]]` — the Playwright MCP server (`playwright-mcp --headless
    --isolated --browser=chromium --no-sandbox`);
  - optional `[scoring] aggregation` (`all_pass` for gate-like dimensions);
  - `[[criterion]]` blocks — `id`, `name`, `type` (`binary` or `likert` with `points`),
    `weight`, and a `description` (the actual test the judge performs in the browser).

---

## 4. The grading model (how a score is produced)

**Five dimensions**, combined as a weighted mean by their `[judge].weight`:

| Dimension | Weight | Criteria (type) | Aggregation | What it measures |
|---|---|---|---|---|
| `functional` | **4.0** | 7 binary (per-criterion weights 1–2) | default (weighted mean) | real product behavior: roles, metrics/activity, order search/filter, order+inventory+payout create/update, **persistence across reload & re-auth** |
| `render` | 2.0 | 2 binary | `all_pass` | app actually renders a substantive authenticated dashboard; all 5 workspaces show distinct content |
| `constraints` | 2.0 | 2 binary | `all_pass` | auth boundary holds; **server-backed, same-origin, durable** (not a static mock) |
| `aesthetic` | 2.0 | 3 likert (points=5) | default | visual hierarchy/craft, marketplace fidelity, production readiness |
| `polish` | 2.0 | 3 binary | default | theme switching, responsive + a11y landmarks/labels, interaction feedback |

Total dimension weight = **12**; `functional` alone is a third of the grade.
`render`/`constraints` use `all_pass` so they behave as gates within their share.

**Two enforcement layers keep the FLOOR low:**
1. **Mechanical (`test.sh`)** — no `server.js`/`index.html`, a symlink, a dead server, or
   a rewardkit crash ⇒ reward 0.
2. **Semantic (global browser gate, in every dimension prompt)** — if protected data is
   visible pre-login, a wrong password is accepted, the app is a static shell, or requests
   are cross-origin, that dimension scores 0. This is what fails a "pretty but fake" app.

---

## 5. Cross-file relationships (the consistency graph)

One runtime contract is asserted in many files; all must agree or the task silently
mis-scores:

- **Port 3000 / `/api/health`** — `instruction.md` ↔ `solution/server.js` ↔ `test.sh`
  (health poll) ↔ `judge.toml` prompts (`http://localhost:3000`).
- **Paths `/app`, `/app/public/index.html`, `/app/bazaarbridge.db`** — prompt ↔ `solve.sh`
  ↔ `test.sh` (existence guard, `DB_PATH`) ↔ `server.js` (`DB_PATH`/`PUBLIC_DIR`).
- **Seed `/assets/artifacts/bazaarbridge_seed_data.json`** — prompt ↔ `environment/Dockerfile`
  (`COPY assets/`) ↔ `solve.sh` ↔ seed-derived expectations in `functional` (Brook search,
  Shipped filter, ≥4 rows).
- **Demo accounts + `password123`** — prompt ↔ `server.js` seeding ↔ every `judge.toml`
  prompt/criteria ↔ the seed `users` list.
- **Judge model + credentials** — `task.toml` (`REWARDKIT_MODEL`, `OPENROUTER_API_KEY`,
  `allowed_hosts`) ↔ each `judge.toml` `[judge].model` ↔ `tests/Dockerfile` codex config.
- **Pre-installed deps + `no-network`** — `environment/Dockerfile` global installs +
  `NODE_PATH` ↔ prompt's "must not install packages" ↔ `[environment].network_mode`.
- **Dimension weights** — `judge.toml` `[judge].weight` values ↔ the single `reward.toml`
  aggregate (rewardkit discovers and combines them).

A half-landed rename or a drifted number anywhere on these edges is the classic defect the
QC rubric must catch.

---

## 6. Data / control flow at run time

**Agent phase (agent image, no network):**
`instruction.md` → agent writes `/app/server.js`, `/app/public/index.html`, uses
`/assets/...` seed → `node /app/server.js` serves on :3000, persists to SQLite.

**Verifier phase (separate image, OpenRouter allowlisted):**
`test.sh` copies `/app` → runs it as `nobody` → health-checks :3000 → `rewardkit /tests`
→ for each `tests/<dim>/judge.toml`, codex/Luna drives Playwright MCP against
`localhost:3000`, applies the global gate, scores each `[[criterion]]` → rewardkit
weighted-means the dimensions per `[judge].weight` and the `reward.toml` aggregate →
`/logs/verifier/reward.json`.

**Oracle validation:** `solution/solve.sh` installs the reference app; the same verifier
scores it and should land near the top (the "ORACLE high" side of the gate).

---

## 7. Format-specific facts the rubric must encode (seed list)

Distilled invariants and failure modes, for the rubric to be written against:

- **Runtime contract fidelity** — port, `/app` paths, health endpoint, seed path, demo
  credentials must be identical across prompt, solution, `test.sh`, and every `judge.toml`.
- **Naming a runtime path/port/credential in the prompt is NOT a scaffolding leak here** —
  unlike trialforge/toolathon, the interface is part of the ask; but naming grader
  machinery (rewardkit, judge, criteria, weights) or tool internals still is.
- **Determinism belongs to the app + judge, not the data** — pinned base image, pinned
  npm deps, seed committed; `temperature = 0` on judges; but browser-LLM judging is
  inherently noisier than deterministic Python — criteria must be **outcome-based and
  binary-decidable** ("create X then confirm exactly one X with these fields after
  reload"), not vague ("looks good").
- **The global browser gate must be present and correct in every dimension** — it is the
  primary FLOOR defense (no static mocks, no pre-login data, real auth, same-origin).
- **Untrusted-evidence clause in every prompt** — prompt-injection defense; the app's own
  text must never be able to dictate its score.
- **Persistence is a first-class criterion** — reload + new sign-in must retain mutations
  (durable SQLite, not in-memory), and `test.sh` runs the app with a relocated `DB_PATH`.
- **Weights are honest** — `functional` (real behavior) is weighted highest; structural/
  aesthetic dimensions must not let a well-styled non-working app score most of the marks.
- **`test.sh` writes a reward on every path** and refuses unsafe `/app` (symlinks, missing
  entry files); a dead app scores 0, not an infra error.
- **Verifier isolation** — grading runs in a separate image the agent can't influence;
  `/tests` is `chmod go-rwx`; the app runs unprivileged with a clean env.
- **Anti-trivial floor to reason about** (the part the oracle/no-op gate can't see): a
  static HTML shell, a client-only mock with no backend, a copied seed with no mutations,
  an app that renders but drops data on reload — each must score low by construction.

---

*Next step: author `rubrics/task-implementation.toml` for webdev using this model — one
`[[criteria]]` block per quality check, organized in blocks (instruction / task.toml wiring /
environment / solution app / tests dimensions & judges / whole-task), each tied to the
two-sided gate and written to resist false findings, mirroring the house style of the
trialforge and toolathon rubrics but targeting browser-judge grading.*
