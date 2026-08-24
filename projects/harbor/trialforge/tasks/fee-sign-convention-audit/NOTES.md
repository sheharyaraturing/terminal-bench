# Fee sign convention audit

**Persona:** Treasury Operations Analyst
**Domain:** software-engineering
**Shape:** 15 claims, 5 servers declared, 16 tools exposed, ~40 tool calls

Ledger values come from data baked into `turing-mcpatlas:0.0.3`: the eight CSVs at
`/data` and the warehouse at `/data/db/turing.db`. The task adds six fixtures (the
committee pack extract, the desk's notes, the rate card, the wire statement, and the
two general-ledger `.sql` extracts), copied to `/data` or loaded into the warehouse by
`environment/Dockerfile`. `task.toml` therefore does **not** set `docker_image`:
`should_use_prebuilt_docker_image()` skips the Dockerfile whenever that key is
present, and the fixtures would silently not exist at run time.

## Fixtures

| File | Contents |
|---|---|
| `crypto-desk-fee-summary.csv` | 14 period rows, one per month the desk reported. They sum to 102.47, the signed sum of the ledger's fee column, which is how the pack's figure was produced. Two rows do not tie period by period: 2023-03 shows -9.72 against -10.72 and 2023-04 shows -12.44 against -11.44, one dollar booked into the wrong month. The two errors offset, so the bottom line still ties and an aggregate-only check misses them. 2023-11 shows 0.00 and the ledger genuinely has no November 2023 activity, so that row is correct. |
| `crypto-desk-pack-notes.txt` | The desk's own note that the line is taken "straight from the export with no adjustment" and has never been agreed to the general ledger. |
| `execution-fee-schedule.txt` | The rate card agreed with the venue: the 0.65 percent contracted cap the fills are run against. Four fills are charged over it, 6.35 recoverable in total; the tiny floor-charge trades are excluded. |
| `general-ledger-fee-postings.sql` | The accounts team's monthly fee postings, loaded into the warehouse. They sum to 226.01, and three months disagree with the export: 2023-01 (posting 7.40 vs 9.20), 2023-09 (94.57 vs 95.47) and 2023-11 (a 10.00 non-trading charge in a month with no trading activity). |
| `general-ledger-fee-detail.sql` | The line-by-line detail behind those monthly postings, loaded into the warehouse. Each month's detail total ties to the export, but 2023-04 does not agree line by line: it carries 3.51 for the export's 3.15 and 0.03 for the export's 0.39. |
| `venue-account-activity-statement.csv` | The venue's separate statement of 13 cash-wire charges totalling 325.00. Twelve tie to a withdrawal; 2023-07-19 is the sole orphan with no withdrawal behind it, making 31.35 recoverable in total (25.00 orphan wire plus the 6.35 over-cap overcharge). |

## The premise

A finance pack reports "total fees paid" from a crypto trade ledger and the number is
too small. The ledger holds 40 negative fee values. They are not corruption: they are
how a fee deducted from sale proceeds is booked. The ledger reconciles on every row.
The defect is downstream, in an aggregation that sums a signed column as though the
sign carried no meaning.

## Ground truth

`CoinbaseTradeHistory.csv` and the `coinbasetradehistory` table hold the same 111
rows, byte for byte identical, 9 columns, no blank cells.

| Fact | Value |
|---|---|
| Rows | 111 |
| Rows with a negative fee | 40 |
| Transaction type of all 40 | `Advance Trade Sell`, without exception |
| Rows with a positive fee | 23, all `Advance Trade Buy`, without exception |
| Rows with fee exactly `0` | 48 |
| `Total == Subtotal + Fees` | holds on all 111 rows, exactly, 0 exceptions |
| Sum of absolute fees (fees actually paid) | 218.71 |
| Naive signed sum (what the pack reports) | 102.47 |
| Understatement | 116.24, equal to 2 × 58.12 |
| Sell-side fee total (the negative rows) | −58.12 |
| Buy-side fee total (the positive rows) | +160.59 |
| Fee / subtotal ratio range | −0.007998 to +0.012500, within ±1.25% |
| Rows with an undefined ratio | 5, subtotal 0.00 with fee 0 |
| Largest fee by absolute size | 35.71, on a buy with subtotal 5,952.00, a ratio of 0.60% |
| Distinct assets | 8: BTC 47, ETH 41, USD 18, XLM/USDC/EOS/DAI/BAT 1 each |
| Transaction types | Sell 42, Buy 30, Receive 17, Withdrawal 12, Deposit 6, Send 4 |
| `USD` rows | 18, all Deposit (6) or Withdrawal (12), never a trade |
| Effective fee rate | buys 0.58% (160.59 on 27,588.64), sells 0.45% (58.12 on 12,925.81), blended 0.54% (218.71 on 40,514.45) over the 72 trade rows |

Sign partition, which is the spine of the task:

```
Advance Trade Sell                42 rows  ->  40 negative,  2 zero
Advance Trade Buy                 30 rows  ->  23 positive,  7 zero
Receive/Withdrawal/Deposit/Send   39 rows  ->  all 39 zero
                                              ---
                                              111
```

Zero-fee rows by type: Receive 17, Withdrawal 12, Advance Trade Buy 7, Deposit 6,
Send 4, Advance Trade Sell 2, totalling 48.

## Derivation

Every figure is computed twice by independent routes and cross-checked.

- Sums and counts: `pandas` over the CSV, and SQL over `turing.db`. Both give 111
  rows, 40 negative, 23 positive, 48 zero, 102.47 signed and 218.71 absolute.
- The accounting identity: exact `Decimal` arithmetic on the stored strings rather
  than floats, giving a residual of exactly zero on all 111 rows.
- Zero-fee count: checked against the literal field text as well as the parsed value.
  All 48 are the literal string `0`.
- Cross-checks that must agree: the sign partition totals 111; 160.59 − 58.12 =
  102.47; 160.59 + 58.12 = 218.71; and the gap 116.24 is twice the sell-side total.
- Ratio range: computed over the 106 rows with a non-zero subtotal. The five excluded
  rows are dust quantities with a subtotal of 0.00, so the ratio is undefined rather
  than extreme.

Column types in the warehouse are all `TEXT`, so numeric comparison and ordering need
an explicit `CAST`. No claim depends on a warehouse column name; the fee, subtotal and
total columns are referred to by role throughout.

## What a correct answer has to establish

Five findings carry the task, and in each the readily available answer is the wrong
one.

1. **The negatives belong to exactly one transaction type.** Counting 40 negative rows
   is an observation. Tying them exclusively to `Advance Trade Sell`, and noticing the
   positives are exclusively `Advance Trade Buy`, is the diagnosis.
2. **Convention, not corruption.** On a buy the fee adds to what leaves the account;
   on a sell it is deducted from the proceeds and booked with the sign of a deduction.
   Both sides satisfy the same identity, so nothing needs repair.
3. **The identity holds on every row, stated positively.** A clean result is easy to
   omit or hedge over when nothing is wrong.
4. **Fees are proportional to the subtotal they sit on.** The largest fee by size is
   35.71 on a subtotal of 5,952, which is 0.60% and entirely ordinary. The ratio, not
   the absolute amount, is what characterises the pricing.
5. **The defect is in the aggregation.** Flipping the signs at source would destroy a
   working reconciliation and leave the reporting bug in place.

## Tool surface

16 exposed across 5 servers, all genuinely usable. sqlite + filesystem are the
primary route; calculator, desktop-commander and cli-mcp-server are redundant-but-
valid routes (they can read the fixtures or do arithmetic). Only the two far-field
dead-end servers (ddg-search, whois) are dropped, since neither can touch the local
ledger or fixtures — success turns on tool discovery, not dismissing servers by name.

Needed:

- `filesystem_list_directory` to find what is in `/data`.
- `filesystem_read_multiple_files` to read the pack extract and the notes.
- `sqlite_list_tables`, `sqlite_get_table_schema` and `sqlite_query` for every
  aggregate. The code-execution server is deliberately not exposed, so each figure
  has to be expressed as a query rather than one script.

Same-server near misses:

- `sqlite_read_records` supports equality conditions only, so it cannot express
  `SUM(ABS(fee))`, a sign filter, or a `GROUP BY`. Routing the whole task through it
  stalls at row listing.
- `sqlite_update_records` is the sharpest trap here, because the wrong answer comes
  with an obvious mutating remedy. `sqlite_delete_records` is deliberately not
  exposed, since it could destroy ground truth mid-rollout.
- `sqlite_db_info` returns metadata only. Every column is declared `TEXT`, so the
  schema says nothing about what the sign means.
- `filesystem_read_text_file` reads one file at a time where the task needs the pack
  extract and the notes together, so it is the slower sibling of the tool that is
  needed. `filesystem_search_files` and `filesystem_write_file` are redundant: the
  ledger sits at a known path and the task writes nothing.
Redundant-but-usable routes:

- `desktop-commander_read_file` / `desktop-commander_get_file_info` and
  `cli-mcp-server_run_command` (ls/cat/find inside `/data`, no pipes) can read the
  fixture files and the ledger CSV. They are slower, redundant paths, not dead ends.
- `calculator_calculate` can do the arithmetic the database aggregates in one query.

Dropped (dead ends, cannot touch the local data): `ddg-search` (web search) and
`whois` (domain lookup). Neither can read the ledger or the fixtures, so they only
work by server-name recognition, which MCP-Atlas is designed to avoid.

## Verification

- All 16 `enabled_tools` names present in `ci/tool_inventory.txt`;
  `sqlite_delete_records` absent.
- The pack extract's 14 period rows sum to 102.47, matching the ledger's signed fee
  sum. Period-by-period, exactly two rows disagree, 2023-03 by +1.00 and 2023-04 by
  -1.00; every other period agrees to the cent and the pack's zero row for 2023-11
  matches the ledger's absence of activity that month.
- Every claim value confirmed against both `/data/CoinbaseTradeHistory.csv` and
  `/data/db/turing.db`, which are identical row for row.
- Both TOML files parse with `tomllib`. Both shell scripts pass `bash -n` and are
  mode 100755 with LF line endings.
- `tests/test.sh` is the shared version from `main`, unmodified.
