# The `turing-mcpatlas:0.0.1` environment

19 MCP servers, **210 tools**, none requiring an API key. Debian 12 + Python 3.12 + Node 20.
Every package version is explicitly pinned.

## Servers

| Server | Tools | Role |
|---|---:|---|
| `desktop-commander` | 26 | file + process operations |
| `wikipedia` | 22 | reference lookup |
| `arxiv` | 14 | preprint search, download, read |
| `filesystem` | 14 | file I/O, rooted at `/data` |
| `git` | 12 | local version control |
| `crossref` | 18 | DOI and citation metadata |
| `paper-search` | 57 | multi-source academic search (21 sources) |
| `mcp-code-executor` | 9 | persistent Python execution |
| `memory` | 9 | entity graph / cross-step state |
| `sqlite` | 8 | local SQL database |
| `open-library` | 6 | books and authors |
| `whois` | 4 | domain registration |
| `cli-mcp-server` | 2 | sandboxed shell |
| `context7` | 2 | version-specific library docs |
| `ddg-search` | 2 | web search |
| `time` | 2 | timezone / date arithmetic |
| `calculator` | 1 | arithmetic |
| `fetch` | 1 | URL retrieval |
| `mcp-server-code-runner` | 1 | one-shot code execution |

## Baked data at `/data`

Deliberately minimal and generic.

- **8 CSVs** — Barber Shop, CoinbaseTradeHistory, Covid 19 impacts on hospitals, Crime_records,
  Pet Care 2023 Weekly Financials, Top Movies, fantasy sports, food and beverage consumption
- **`/data/db/turing.db`** — SQLite seeded from those CSVs: 8 tables, 480 rows

| Table | Rows | Cols |
|---|---:|---:|
| `coinbasetradehistory` | 111 | 9 |
| `food_and_beverage_consumption` | 80 | 11 |
| `crime_records` | 71 | 10 |
| `pet_care_2023_weekly_financials` | 52 | 9 |
| `fantasy_sports` | 51 | 10 |
| `top_movies` | 50 | 9 |
| `covid_19_impacts_on_hospitals` | 34 | 7 |
| `barber_shop` | 31 | 7 |

**No git repositories are baked in.** This is deliberate — see *Fixtures* below.

## Fixtures: tasks bring their own

The base image ships no task-specific data. Anything your task needs, it supplies through its own
`environment/` directory, which **is** the Docker build context. This follows Harbor's documented
pattern (see its ScienceAgentBench adapter).

This is a normal image build on the host Docker daemon. **It is not docker-in-docker** —
`FROM turing-mcpatlas:0.0.1` is simply a base layer.

### Git repositories: use a bundle

Do not `git clone` from a URL at build time, and do not vendor a raw `.git` directory.
Use a **git bundle** — one file, full history, no network, immune to upstream deletion.

Create it once:

```bash
git clone https://github.com/org/repo /tmp/repo && cd /tmp/repo
git bundle create repo.bundle --all
```

Commit it to `environment/fixtures/repo.bundle`, then in your `environment/Dockerfile`:

```dockerfile
FROM turing-mcpatlas:0.0.1
COPY fixtures/repo.bundle /tmp/
RUN git clone /tmp/repo.bundle /data/repos/repo && rm /tmp/repo.bundle
ENTRYPOINT []
```

Measured on a 631-commit repo: the bundle is **8.9 MB in one file** versus 9.6 MB across thousands
of loose objects for a vendored clone. Cloning from the bundle restores all 631 commits exactly.

Two rules:
- **Never `--depth 1`.** `git_git_log` needs history; a shallow clone gives you one commit.
- **Never a moving branch.** Bundle a fixed state. A floating ref means your ground truth rots.

---

## Gotchas

Every one of these has cost real debugging time. Read them before you author.

### Tool names carry a double prefix on some servers

The agent calls `git_git_log`, **not** `git_log`. Calling `git_log` returns `Unknown tool`.

The server's tools are already named `git_*` internally, and the MCP client prefixes with the
server name on top. Same for `whois` → `whois_whois_domain`.

Always confirm the real name from `/list-tools` rather than assuming.

### `wikipedia` registers 22 names but only ~11 are distinct

Both `search_wikipedia` and `wikipedia_search_wikipedia` exist and do the same thing. Treat the
duplicates as built-in distractors, not extra capability.

### `cli-mcp-server` is not a shell

Locked to `ls`, `cat`, `find`, inside `/data` only. No pipes, no redirects, no shell operators,
30-second timeout. If your task needs real shell work, use `mcp-code-executor`.

### `filesystem` is rooted at `/data`

Paths outside it are refused.

### Every `git` tool needs `repo_path`

There is **no** `git_init` — it has never shipped in any version of this server, despite appearing
in some published tool listings. Repositories must already exist in the image.

Repos baked via a task Dockerfile land in detached HEAD if you check out a SHA. Add
`git checkout -b main <sha>` if your task expects a branch name.

### `sqlite` CRUD tools are exact-match only

`read_records`, `update_records`, `delete_records` support equality conditions only. Ranges,
`LIKE`, `JOIN`, and `ORDER BY` must go through `sqlite_query`.

Note `sqlite_query` can also do everything the CRUD tools do, so a task only genuinely *requires* a
specific CRUD tool if the prompt constrains the agent to it.

### Harbor does not gate tools

`[[environment.mcp_servers]]` has exactly five fields: `name`, `transport`, `url`, `command`,
`args`. There is **no `enabled_tools`** field — extra keys are silently dropped. Whatever a server
advertises, the agent sees. Control the tool surface by choosing which servers to declare.

### Pin `mcp<2` on every uvx server

`mcp` 2.0.0 is a breaking release of the Python SDK: `McpError` was renamed, `mcp.server.fastmcp`
was removed, and `Server.list_tools()` disappeared. Pinning only the *server* version is not
enough — the transitive SDK floats to 2.0.0 and the server crashes on import, then **silently fails
to register**. The task template already carries `--with mcp<2`; keep it.

---

## Exploring the environment yourself

```bash
docker run -d --name mcpatlas -p 1984:1984 turing-mcpatlas:0.0.1
```

```bash
curl -s -X POST http://localhost:1984/list-tools | python3 -m json.tool | less
```

The live container is the only trustworthy source for tool names and descriptions. Published
listings have been wrong more than once.

### Subsetting servers

`ENABLED_SERVERS` limits which servers start. Measured:

| Servers | Memory | Boot | Tools |
|---:|---|---|---:|
| 19 (all) | 2.1 GB | ~60 s | 210 |
| 7 | 1.0 GB | ~25 s | 48 |

Useful for local exploration. Note this is a container-level env var, not something Harbor sets
per task — in a task you control the surface by declaring fewer `[[environment.mcp_servers]]`.
