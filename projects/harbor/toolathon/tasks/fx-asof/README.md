# context-mesh/fx-asof

Restate multi-currency revenue in USD at the rate in force on each transaction date.

Sixty posted transactions in seventeen currencies have to be carried into the group reporting currency. The arithmetic is one multiplication; the task is deciding *which rate* each row gets. The frozen vendor snapshot publishes only on days its fixing calendar is open, one currency's coverage opens only part-way through the period, another redenominated inside it, one is not in the snapshot at all, and the reporting currency itself is not converted. Every one of those is settled by `metrics/FX_Policy.md`, which the agent has to find, read past the parts it expected, and apply row by row. The prompt itself is [instruction.md](instruction.md).

- **Tools** — MCP servers `filesystem,terminal,excel,word,pptx`, local tools `claim_done`, all behind the one SSE gateway on `127.0.0.1:8765`. `word` and `pptx` are declared and unused.
- **Verifier** — `tests/artifacts/`, `tests/conversion/` and `tests/workings/`, aggregated by `tests/reward.toml`. Every criterion is a fraction. `artifacts` scores structure only — the seven columns, their stated order, the stated sheet name, the eight JSON keys — and every one of its criteria is gated on the artifact carrying at least one data row, so a headers-only shell scores 0.000 overall rather than banking a third of the reward. `conversion` scores the restated amount, the provenance of the quote used (its date, its value, its basis), the source fields carried through and the stated row order, keyed on `Txn_ID` with `max(len(expected), len(got))` as the denominator so padding cannot inflate it; `workings` scores the total to the cent, the per-currency counts, the carried-forward count and the undefined accounting, with the period pin gated on a restatement existing at all because section 7.2 publishes those three strings verbatim. `UNDEFINED` is matched as a literal string, so `0`, `""`, `null` and a missing row are all rejected.
- **Everything else** — environment, gateway and eval chain are the suite template's, unmodified. See `docs/task-structure/`.

## Regenerating

```bash
python3 tasks/new_task.py lint tasks/generated/fx-asof
python3 tasks/new_task.py gate tasks/generated/fx-asof
```

Recorded before the local dry-run harness was removed: `oracle=1.000  nop=0.000  naive=0.560`. A headers-only stub of both deliverables scores `0.000`, whether its `workings.json` is empty or copies section 7.2's skeleton verbatim.

### Ordering and layout

Section 7.1 states three layout requirements, and all three are graded rather than merely stated: the sheet name (`artifacts.sheet_name`), the column order (`artifacts.column_order`, fraction of the seven at their stated index) and the row order (`conversion.row_order`, fraction of rows sitting where `Txn_ID` ascending puts them). `conversion` still keys the money on `Txn_ID` so a misordered sheet loses the ordering fraction rather than every fraction.

### Formulas

Section 7.1 states that computed values are recorded rather than formulas, so a formula-bearing cell breaks a stated rule and scoring it wrong is enforcement. The grader does not try to evaluate it — openpyxl has no formula engine — it loads the workbook twice and, where the cached read is blank, carries the formula text through so the mismatch reads as `'=C3*E3'` and not as `(blank)`, and prints one line per affected sheet naming the cell and the section it breaks. A cell holding nothing but a literal (`=2418.63`) is recovered, because that needs no engine.

## Difficulty budget

| Lever | Instance |
|---|---|
| L1 overlong observation | **One of the two vectors is instantiated.** `reference/fx_rates.csv` — sixteen currencies over three calendar years, 9,837 rows — measures 255,795 chars rendered, 2.6× the Toolathlon agent's 100,000-char ceiling (`MAX_SINGLE_TURN_RETURN_CHARS`, the loop's own log line); Harbor's built-in agents truncate near 8–10 KB, but they never reach the MCP gateway and this suite is not measured under them, and cannot be read whole. `transactions.csv` measures 11,760 chars and arrives whole, so it is a second vector on breadth, not on truncation. The image supplies the means: the `terminal` server is declared and section 8 of the policy states the navigation path (`grep` a currency code, `awk` a date range, or read it with the `csv` module from a script). |
| L2 observation floor | The policy states `transactions.csv` holds 96 rows, so a truncated first read is visibly short. Premature-stop lure: `reference/fx_rates_budget.csv`, a 32-row table that answers every currency in a single un-truncated call and is wrong for every one of them. |
| L3 prior contradiction | *Prior:* a period's revenue is converted at the closing rate → *environment:* section 3 converts at the rate published on each transaction's own date, "not period-end, not the latest rate in the snapshot, not an average over the period". *Prior:* a gap in a daily series is filled by interpolation → *environment:* carry the last published quote forward, never blend. *Prior:* "two decimal places" → *environment:* half-up in exact decimal, with one value sitting exactly on the half cent. |
| L4a parameter/resource strictness | Rates are published to eight decimal places and are only obtainable by looking up the `(currency, quote_date)` pair; the quote direction is `usd_per_unit`, not units per USD. No constructed or remembered rate survives, and `1.08650000` is not guessable. |
| L4b tool-name confusability | `word` and `pptx` are declared in `MCP_SERVERS`; the workspace holds no `.docx` and no `.pptx`, and no step needs either. |
| L5 state distractors | 36 of the 96 ledger rows are outside the population — 22 dated either side of the period, 14 `void` or `draft` inside it — a ratio of 0.6 irrelevant rows per relevant row. Five of the distractors are struck in the awkward currencies (`NGN`, `TVR`, `PLN`) so the exclusion cannot be inferred from currency alone. `reference/fx_rates_budget.csv` adds a second, non-authoritative rate source. The policy never mentions it: section 3 names the snapshot and says a usable rate has to carry a `quote_date` and has to have come out of that file, and the budget table carries `plan_year` and `approved_by` instead — so the exclusion is inferable from evidence rather than announced. The same holds for `metrics/Format_Example.xlsx`: its illustrative row names `TX-EXAMPLE` in `XTS` on 1999-01-04, none of which survives section 2's population test. |
| L6 restraint | `TX-1030` and `TX-1077` are struck in `NGN`, which the snapshot does not carry at any date. They must come back `UNDEFINED` with the reason `NO_RATE_FOR_CURRENCY` — not zero, not blank, not omitted, and not converted at a neighbour's rate. |
| N1 population from a definition | The row set is not handed over: the policy's two conditions (`txn_date` inside the pinned period, both bounds inclusive; `status` equal to `posted`) select 60 of 96. |
| N2 null / zero / absent | Three different things and the policy separates all three: an undefined row still appears in the workbook and still counts in `transactions_by_currency`, but contributes nothing to `total_usd_revenue` and is never carried forward; `undefined_by_reason` must carry both reason keys explicitly rather than omitting either (section 7.2 pins a literal `0` where a reason did not occur; here both occurred, 2 and 1); an excluded `void` row appears nowhere at all and is *not* reported as undefined. |
| N3 point-in-time | The whole task. Nineteen of the sixty rows resolve to a quote dated before the transaction, one currency changes scale mid-period, and one currency's coverage opens mid-period. |
| Traps | Eight, below. |

## Traps

| Trap | Where | Punishes |
|---|---|---|
| Saturday transaction on the period-start bound | `TX-1012`, EUR, 2023-04-01 | Interpolating across a gap: carrying 2023-03-31 forward gives 562,080.13, straight-lining to the Monday quote gives 562,098.87. Also punishes an exclusive lower bound, which drops the row entirely. |
| Holiday behind a holiday | `TX-1017`, GBP, 2023-04-10 | "A weekday has a rate", and a one-day-back carry: Easter Monday and Good Friday are both closed, so the quote walks back to 2023-04-06. |
| Transaction already in the reporting currency | `TX-1023` and `TX-1065`, USD, both on a Sunday | Converting USD anyway. A model that looks USD up in the snapshot carries Friday's quote forward, writes `CARRIED_FORWARD` and the wrong `Rate_Date`, and inflates `carried_forward_count` above 19. |
| Currency absent from the snapshot | `TX-1030` and `TX-1077`, NGN | Inventing a rate, substituting a proxy or a peg, or silently dropping the rows. |
| Coverage that opens mid-period | `TX-1025`, PLN, 2023-04-20 (coverage opens 2023-05-10) | Carrying a quote *backwards*, and "the currency is in the snapshot, therefore it converts" — `TX-1067` in the same currency converts normally, so a per-currency decision is wrong. |
| Redenomination inside the period | TVR, scale step on 2023-05-15 from 0.00041997 to 0.42089; two transactions before, three after | One rate per currency — period-end, latest, or a period average — which restates the pre-step rows a thousandfold. |
| A product landing exactly on the half cent | `TX-1054`, EUR 2,010.00 × 1.08650000 = 2183.865 | Banker's rounding, which is `Decimal`'s default and Python's `round`, and gives 2183.86 against the policy's 2183.87. |
| Transaction on the period-end bound | `TX-1085`, GBP, 2023-06-30 | An exclusive upper bound, which drops a 237,896.04 row from the total. |

The naive method is the check on all eight: it filters the population correctly, produces a well-formed workbook in the stated sheet, column and row order, and a complete `workings.json`, and strikes every row at the closing rate in binary floating point. It scores 0.560 — 15% of the amounts and 5% of the provenances right, the total wrong by 17.3 million, `carried_forward_count` at 0 against 19, and one of the two undefined reasons missed.

## Restraint case

The two `NGN` transactions. The snapshot carries no `NGN` row at any date and the policy forbids a proxy, so the only correct disposition is to keep the rows in the population, mark `Rate_Date`, `Rate` and `USD_Amount` as the literal `UNDEFINED`, record `NO_RATE_FOR_CURRENCY`, and let them contribute nothing to the total. Flagging, not guessing, and not deleting.

## Known coverage gaps

Waived deliberately: closing each of these means moving a seeded row, which rewrites `tests/expected/` and re-derives an answer key that is verified correct today. The documented gap is the better trade.

- **No transaction sits exactly on PLN's coverage-open date.** Section 4's `NO_RATE_ON_OR_BEFORE_DATE` turns on "publishes nothing dated *on or before* the transaction date". PLN's first quote is 2023-05-10; the two PLN population rows are `TX-1025` (2023-04-20, undefined) and `TX-1067` (2023-06-05, converted). A row dated 2023-05-10 itself would separate "on or before" from "strictly before" at coverage start; none exists, so an off-by-one there is not caught by the key.
- **Section 7.2's explicit `0` is stated but not exercised.** Both reason codes have nonzero counts here (2 and 1), so the difference between writing `0` and omitting the key is never the deciding fact. The grader does reject a missing key — a stub omitting both scores `undefined_accounting` 0.000 — so this is a gap in the data, not in the grading.
- **The period's upper edge is tested less tightly than its lower edge.** `TX-1011` sits on 2023-03-31, one day below the period. Above it the nearest out-of-scope posted row is `TX-1086` on 2023-07-03, three days out. `TX-1085` on 2023-06-30 still catches an exclusive upper bound, so no graded outcome changes.
