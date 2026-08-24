# Tool allowlists

The allowlist lives in `task.toml` under `[metadata] enabled_tools` — there is no separate file. The
wrapper passes it through as the harness's `enabledTools`, which filters **client-side**
(`tools.filter(t => enabledTools.includes(t.name))`), so a typo silently drops a tool instead of
erroring. Copy names verbatim from `/list-tools` — double prefixes (`git_git_log`,
`whois_whois_domain`) are real — and assert `enabled_tools ⊆ /list-tools` before every run.

MCP-Atlas exposes a mean of 15.2 tools of which 4.11 are needed: 3.6 same-server siblings and 7.5
off-server — **2.7 distractors per needed tool, at roughly 1 same-server : 2 off-server**. The skill
measured is tool *selection* under a crowded surface, not tool *use*. Our tasks run 40–70 calls and
genuinely need 8–11 tools, so holding the surface at ≤30 caps the ratio near 1.6–2.3:1.
**Preserve the 1:2 composition, not the raw ratio** — the composition is what makes the choice hard.

| Task | Exposed | Needed | Same-server | Off-server | Ratio |
|---|---:|---:|---:|---:|---:|
| warehouse-csv-reconciliation | 26 | 8 | 6 | 12 | 2.25 |
| eight-table-data-profiler | 29 | 11 | 6 | 12 | 1.64 |
| bootstrap-interval-validity | 28 | 10 | 6 | 12 | 1.80 |
| hospital-occupancy-statistic | 29 | 11 | 7 | 11 | 1.64 |

## Rules for task 5 onward

1. **Never dump a server.** `paper-search` has 57 tools, `wikipedia` 22 (11 aliases),
   `desktop-commander` 26. Take 1–3 from each; a dumped server is noise, not a distractor.
2. **The best distractors are near-misses:** a redundant read path (`desktop-commander_read_file`
   beside `filesystem_read_text_file`), a crippled one (`cli-mcp-server_run_command` — no pipes,
   `/data` only), a wrong index (`paper-search_search_biorxiv` for a published-summary question), a
   wrong medium (`open-library_get_book_by_title`), a name alias (`wikipedia_wikipedia_get_summary`).
3. **One or two far-field distractors** (`whois_whois_domain`, `time_get_current_time`) test whether
   irrelevance is noticed at all. More than two just burns context.
4. **Mutating siblings are legitimate traps** — `sqlite_update_records` tempts an agent to "fix"
   drift it was asked to *report*. Never expose `sqlite_delete_records`: it can destroy the ground
   truth mid-rollout and make a bad rollout unrepeatable.
5. **Demote to distractor only if the task survives without it.** `install_dependencies` is safe to
   demote only because numpy/pandas/scipy 1.16.0 are already in the code-executor venv.
6. **Classify per task** — `calculator_calculate` is needed for the reconciliation delta and pure
   redundancy in the hospital task. And `[environment.mcp_servers]` is *not* the allowlist and is
   unused at runtime; `enabled_tools` may name any of the image's 210 tools.
