# NOTES — journal-balance-forensics

## Premise

A Financial Systems Analyst has to hand the external auditors a findings memo on
two quarters of general-ledger postings. The extract does not foot, and the
naive reading — group by entry, subtract credits from debits — finds the whole of
the difference in five entries. That is Layer 1 and it is one group-by away.

The task is what is left after that. Once the five imbalances are set aside the
ledger foots to the cent, so a model that stops there produces a clean-looking
memo that misses both real control failures:

- a **balanced** entry posted twelve days after its accounting period was
  closed. Invisible to any debit/credit test, and invisible to the journal file
  on its own — the close dates live in a separate reference table.
- a **balanced** reversal that does not reverse. The amount was negated; the
  currency was not carried over, so an 18,450.00 EUR expense is still on the
  books while an 18,450.00 USD expense that was never posted has been removed.
  Both entries in the pair balance internally, which is precisely why the
  Layer-1 test cannot see it.

Two decoys are planted so that a shallow pass produces false positives rather
than merely omissions.

## Fixture provenance

Both artefacts are **synthetic and authored here**. Nothing was downloaded and
no upstream ledger was used.

| artefact | injected as | measured size |
|---|---|---:|
| `fixtures/journal.jsonl` | `COPY` to `/data/journal.jsonl` | **103,346 bytes** (400 lines) |
| `fixtures/extra.sql` | `sqlite3 /data/db/turing.db < …` | **1,500 bytes** (9 INSERTs) |
| `fixtures/GROUND_TRUTH.md` | not injected — authoring artefact | 6,122 bytes |

Build invocation:

```
bash environment/fixtures/build_fixture.sh
```

It was actually run. Determinism was verified by copying the script alone into an
empty directory, re-running it, and diffing:

```
journal.jsonl  sha256 83a39635d543d9f5153eb9f0c55c6ad27fd60366083dd57e3a022afafb5920a7
extra.sql      sha256 700a0ab750e62780480ac3971d95dd14b8400bcceaffa35bcd40d5178e53e717
```

Both checksums, and `GROUND_TRUTH.md` byte-for-byte, reproduced from the clean
directory. The only entropy source in the script is `random.Random(20240815)`,
consumed in a fixed order; every special entry is written from a literal table.

No pinned SHA — this task ships no git fixture.

`extra.sql` issues one `CREATE TABLE IF NOT EXISTS gl_period_close` plus nine
`INSERT`s and **nothing else**. It does not read, alter, rename or drop any of
the eight tables baked into `turing.db`, which are shared with other tasks in
the suite. Column types follow the baked convention (all `TEXT`, since
`close_date` is empty for the two periods that are not closed and `period` is a
`YYYY-MM` label).

## Ground-truth read-back

`environment/fixtures/GROUND_TRUTH.md` is **generated**, not written by hand. The
read-back stage at the bottom of `build_fixture.sh` shares no state with the
builder: it re-opens `journal.jsonl` and parses it line by line, and it obtains
every period-close fact by executing `extra.sql` into a scratch SQLite database
and querying it back with SQL. Whatever that stage prints is the file.

The values it produced, all of which appear in `tests/reward.toml`:

- 400 lines / 140 entries / 14 accounts / 9 period-close rows
- five unbalanced entries: JE-0018 +360.00, JE-0047 −0.50, JE-0073 +40,500.00,
  JE-0098 −36.00, JE-0121 −1,120.00
- signed total 39,703.50; absolute total 42,016.50; largest JE-0073
- whole file: debits 3,828,680.79 vs credits 3,788,977.29
- with the five excluded: 3,739,435.04 on both sides, difference 0.00
- six entries posted outside their period month; **exactly one** (JE-0064) posted
  after that period's close date — 2024-05, closed 2024-06-07, posted 2024-06-19,
  12 days late, 26,750.00 USD, balanced
- near-miss JE-0082 — 2024-06, closed 2024-07-05, posted 2024-07-05, i.e. *on*
  the close date, legitimate
- six reversal pairs; **two** do not offset: JE-0079 (EUR) / JE-0106 (USD),
  18,450.00, mismatched on currency; and JE-0131 / JE-0138, 15,300.00 USD,
  mismatched on account (JE-0131 debits 6100 Depreciation but JE-0138 credits
  5400 Facilities instead of 6100)
- account 5210 Professional Fees is touched by exactly two entries in the whole
  file, giving a clean residual of +18,450.00 EUR and −18,450.00 USD
- one all-zero entry: JE-0055, balanced at 0.00
- second reversal defect: JE-0138 reverses JE-0131 on the right currency (USD)
  and amount (15,300.00) but credits the wrong account, so the 6100 depreciation
  charge is never actually reversed

One thing the read-back caught that the build script did not intend to guarantee:
the six out-of-month postings are what make the cross-reference load-bearing. If
there had been only two (the defect and the near-miss) the finding would have
been reachable by `posted_at[:7] != period` alone, with no need for the
period-close table at all. The read-back table in `GROUND_TRUTH.md` is what
confirmed the count is six and that five of them are clean.

## Difficulty design

Claim order is Layer 1 → Layer 2 → decoys, exactly as the coverage curve wants:
a model that stops at Layer 1 banks claims 1–6 and drops claims 7–14.

16 claims, all weight 1.0, scored as a plain mean. A model that stops at Layer 1
banks the shape and imbalance claims and drops the layered findings behind them.
The hard claims sit in two clusters a debits-versus-credits check cannot see: the
entry posted after its period closed, and the two reversals that do not offset
(one on currency, one on the account it credits).

The hard claims and why a strong model drops them:

1. **JE-0064 is the only entry posted after its period closed** (claim 7). The
   model must realise that "closed" is a fact it does not have. The prompt never
   mentions a close date, a close register or a period status; it says "when they
   were booked". A model that reasons entirely inside the journal file cannot
   even form the question.
2. **The close date is 2024-06-07 and the lag is 12 days** (claim 8). This is the
   claim that separates a real cross-reference from a shortcut. Six entries are
   posted outside their own period month; five are legitimate. A model that
   flags "posted_at month != period" reports six findings, five of them wrong,
   and fails this claim even though it named JE-0064 among them.
3. **JE-0064 balances** (claim 9). Requires stating the negative — that the
   Layer-1 instrument is blind here. Models tend to report a finding without
   saying what would not have found it.
4. **JE-0079/JE-0106 is the pair that does not offset** (claim 10). Five reversal
   pairs exist and four are clean. Finding them at all requires reading the memo
   text, not the amounts; nothing in the numeric columns distinguishes them.
5. **The cause is the currency, not the amount** (claim 11). This is the single
   most-likely miss. Both entries balance, both are for 18,450.00, the accounts
   mirror correctly and the signs are right. Every quantity a reconciliation
   normally checks is correct. Only the `currency` field is wrong, and a model
   that has been summing `debit` and `credit` for fifty tool calls has no reason
   to project onto currency — grouping by currency also shows nothing, because
   every entry balances *within* its own currency.
6. **The residual is +18,450.00 EUR against −18,450.00 USD** (claim 12). Requires
   holding the two currencies apart instead of collapsing them. A model that
   reports "the pair nets to zero" fails, and that is the natural summary.
7. **JE-0055 must be excluded** (claim 13). A zero-amount line is the canonical
   ledger smell. Any "flag lines where debit = 0 and credit = 0" rule catches it,
   and it is a legitimate placeholder accrual.
8. **JE-0082 must be excluded** (claim 14). It sits one day inside the boundary:
   posted 2024-07-05, which is period 2024-06's close date, not a date after it.
   A model using `>=` instead of `>` reports it and fails.

Levers used, against the conventions' list: layered defects (1), a claim that
depends on a quantity the prompt never mentions (2 — the close date), a required
cross-reference between the file and the warehouse (3), decoys that survive
casual checking (4 — two of them), and a required direction/sign discrimination
(5 — which currency is over- and which under-stated).

## Tool surface

26 exposed, 8 needed, 6 same-server distractors, 12 off-server distractors —
distractor:needed ratio 18/8 = 2.25, holding the 1 same-server : 2 off-server
composition. 11 servers, 4 of them carrying needed tools. `sqlite_delete_records`
is not exposed anywhere.

Sharpest distractors:

- `sqlite_read_records` — an equality-only filter. It can fetch the close table
  but it cannot express `posted_at > close_date`, which is the entire
  cross-reference step. A model that reaches for it gets rows and no answer.
- `sqlite_update_records` — the mutating sibling. The persona asks for a memo;
  this tool tempts a model into "correcting" JE-0073's credit, which destroys the
  ground truth mid-rollout and answers a question nobody asked.
- `time_convert_time` — a genuinely plausible wrong turn. Postings dated outside
  their period month look like a timezone artefact, and there is a tool right
  there for timezone maths. It is the wrong reading; the periods are labels, not
  instants.
- `cli-mcp-server_run_command` — no pipes and `/data` only, so the reflexive
  `cat journal.jsonl | jq ...` is unavailable and a model that commits to it
  burns calls.
- `mcp-code-executor_install_dependencies` — a dead end twice over: pandas is
  already present and the image has no egress.
- `whois_whois_domain`, `ddg-search_search` — far-field; a model that searches
  the web for double-entry rules has misread the task as knowledge-bound.

## Realism trade

The fixture is synthetic. A real general ledger would be messier: more accounts,
inconsistent memo conventions, intercompany lines, FX revaluation entries, and
imbalances that arise from genuine subledger timing rather than from authored
transposition errors. The trade is deliberate and it buys full knowability — every
claim quotes a value read back out of the artefact, with no `[DERIVE]` and no
guessing about an upstream system.

The claim structure would survive a swap to a real extract, because each claim
describes a *pattern* rather than a particular company: entries that do not foot,
a balanced posting later than its period's close date, a reversal that negates the
amount but not the currency, a zero-value entry that is legal, and a boundary case
at exactly the close date. Re-pointing the fixture would mean re-running the
read-back stage and re-writing the numbers; the phase chain and the weighting
would not change.

## Cross-task overlap

`gl_period_close` is a new table, created only by this task's `extra.sql`, and
`/data/journal.jsonl` is a new path. Neither collides with the eight baked tables
or with the other v2 fixtures. The tool allowlist overlaps heavily with other
sqlite/filesystem tasks in the suite, which is intended — the allowlist is not a
differentiator.

## Not verified

- **No container was booted.** `environment/Dockerfile` was not built. The
  `COPY`/`RUN` lines and the four build-time assertions are reasoned from the
  template's documented injection routes, not from a successful `docker build`.
  `sqlite3` is assumed present in the base image because the template's own
  Dockerfile comment uses it; that assumption is untested here.
- **The task was not run.** No agent and no oracle execution happened, so
  "the oracle scores 1.0" is an argued property, not a measured one: every claim
  in `tests/reward.toml` was checked by hand against
  `solution/solve.sh` and against `fixtures/GROUND_TRUTH.md`, and each of the 14
  has a corresponding passage in the oracle answer.
- **The judge was not invoked.** No OpenRouter call was made; claim wording has
  not been exercised against `openrouter/anthropic/claude-sonnet-5`.
- **The difficulty target is design intent, not measurement.** No Kimi-K3 or
  GLM5.3 rollout was performed. The claim that those models land a partial pass
  rests on the weighting arithmetic above and on the argument for each weighted
  claim, not on observed coverage.
- **`target_tool_calls = 58` is an estimate**, not a measured trajectory length.
- The fixture's `extra.sql` was executed only against a *scratch* database
  created from the SQL itself. It was never executed against the real
  `/data/db/turing.db`, so the assertion that it leaves the eight baked tables
  untouched rests on reading the SQL (one `CREATE TABLE IF NOT EXISTS` and nine
  `INSERT`s, no `DROP`, `ALTER` or `UPDATE`) rather than on a before/after
  comparison of that database.
