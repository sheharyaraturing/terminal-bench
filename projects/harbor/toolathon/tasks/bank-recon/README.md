# context-mesh/bank-recon

Reconcile a bank statement against the AP ledger under the stated tolerances.

A month of bank activity has to be reconciled against accounts payable. The arithmetic is trivial; the difficulty is that nothing about the match is the shape a default matcher assumes. Amounts agree only within two pence, references agree only after a stated normalisation, dates agree only in business days measured against a holiday calendar the data does not imply, one payment settles three invoices, one invoice is paid twice, one payment is reversed, and one reference fits two invoices equally well and must be flagged rather than resolved. Every one of those rules lives in `sop/Reconciliation_Procedure.docx` inside the workspace; the prompt states the goal and the artifact and nothing else. The prompt is [instruction.md](instruction.md).

- **Tools** — MCP servers `filesystem,terminal,excel,word,pptx`, local tools `claim_done`, all behind the one SSE gateway on `127.0.0.1:8765`.
- **Verifier** — four Reward Kit dimensions under `tests/`: `artifacts`, `matched`, `unmatched_bank` and `unmatched_ledger`. Every dimension scores a fraction of graded cells, never a boolean, and divides by `max(len(expected), len(produced))` so padding a sheet lowers the score. `artifacts` grades the shape §8.1 fixes and nothing is paid for an empty shell: each of its three criteria counts a sheet only when that sheet carries at least one data row, so a headers-only workbook scores 0.000 overall, not 0.250. The three criteria are the columns, the sheet and column order (positional, one point per position) and the row sort (the key column compared position by position against the key). Sheets are found by name or by header rather than through `.active`; `unmatched_bank` rejects blank, `0`, `None`, `-` and a missing column where the procedure requires the `N/A` sentinel; and a cell holding a formula with no cached value is named in the log — `matched: Matched!G2 holds the formula '=E2-F2' and no cached value; section 8.6 of the procedure requires recorded values, not formulas` — once per affected sheet, then compared as written, because §8.6 requires recorded values.
- **Everything else** — environment, gateway and eval chain are the suite template's, unmodified. See `docs/task-structure/`.

```bash
python3 tasks/new_task.py gate tasks/generated/bank-recon
```

## What the agent has to work out

`bank_statement.csv` is 3,000 lines and 236 KB. 187 of them are accounts payable; the other 2,813 are payroll, card settlements, direct debits, bank charges, interest and treasury sweeps. `ap_ledger.xlsx` carries 210 invoices, 204 of them in scope. 176 statement lines settle 178 ledger entries; 11 statement lines and 26 ledger entries do not, each for one of twelve stated reasons.

## Difficulty budget

| Lever | Instance |
|---|---|
| L1 overlong observation | **Instantiated.** One vector: `bank_statement.csv`, 3,000 lines, measured at 241,352 chars rendered — 2.4× the Toolathlon agent's 100,000-char ceiling (`MAX_SINGLE_TURN_RETURN_CHARS`, the loop's own log line); Harbor's built-in agents truncate near 8–10 KB, but they never reach the MCP gateway and this suite is not measured under them. Even `grep SUPPLIER-` returns ~16 KB, so one filter is not enough. §1 of the procedure names the navigation path — `grep`, `rg`, `awk -F,`, `sort`, `head`, and `python3` with the `csv` module, which bypasses the boundary entirely. |
| L2 observation floor | 14 independent facts, none inferable from the records: the in-scope channel list; the in-scope statuses plus the two window bounds; the canonical date form against the statement's day-first form; the four-step reference normalisation; the 0.02 amount tolerance and its inclusivity; the 3-business-day tolerance and its inclusivity; the two bank-holiday dates; ROUND_HALF_UP and that rounding precedes the tolerance test; the seven-code statement reason ladder and its precedence; the five-code ledger reason ladder and its precedence; one-settlement-per-entry with the earliest-value-date tie-break; the reversal-pair definition; the `N/A` sentinel and its two occasions; the sheet names and column order in `sop/Format_Example.xlsx`. |
| L2 premature-stop lure | `archive/reconciliation_2026-03.xlsx` is a finished reconciliation in exactly the required shape, and 170 of the 187 in-scope lines settle on a first naive pass, so the job reads as ~91% done before any of the seventeen hard lines has been looked at. Nothing in the prompt or the procedure points at it or excludes it; it is distinguishable by evidence only — the `archive/` directory, the file name, the document title and subject (`Statement period 1 March 2026 to 31 March 2026`) and every date inside it are March, against the April period §2 pins. |
| L3 prior contradiction | Five, each written as *prior → environment*. (a) A match means equal amounts → 40 settlements differ by one or two pence, and 0.02 passes while 0.03 does not. (b) One payment settles one invoice → `TXN1438` settles three in one payment run. (c) "Within three days" means calendar days → it means business days, excluding 2026-04-03 and 2026-04-06, so `TXN0500` is three days apart across a seven-day span. (d) Amount magnitude is enough to identify a settlement → a positive line is a reversal and settles nothing. (e) Match, remove, move on → a second line for a settled entry is `DUPLICATE_PAYMENT`, not "no match". |
| L4a parameter/resource strictness | Four lookups that defeat a constructed guess: the two bank-holiday dates, which nothing in the records implies; `PAID` being in scope while `ON_HOLD` is not, so guessing "PAID means already reconciled" drops `AP0194` and `AP0201`; the window opening on 2026-03-23, nine days before the statement period, so guessing "April" drops `AP0181`; and the exact column names and order, published as data in `sop/Format_Example.xlsx` rather than as prose. |
| L4b tool-name confusability | Five servers declared, two of them Office-document servers that shade into each other (`word`, `pptx`) alongside `excel`. `pptx` is never needed — no deliverable is a deck — and `word` is read-only here, used once to open the procedure. |
| L5 state distractors | 2,813 out-of-scope statement lines to 187 in-scope, 15.0 : 1; and 6 out-of-scope ledger entries to 204 in scope, 1 : 34. Three of the out-of-scope lines wear invoice-shaped references (`INV-2455` on `INTERNAL-XFER`, `INV-1042` on `CARD-STL`, `INV-1105` on `DD-UTIL`); §3.1 says Channel is the only scope test and never says that some references are decoys, so the `Channel` column is the evidence that separates them, and skipping the channel filter invents duplicate settlements. |
| L6 restraint | One case. `TXN2255` references `INV-0000712`, which normalises to `INV712`; `AP0178` (`INV-712`) and `AP0179` (`INV-0712`) are the same vendor, the same amount and both inside the date tolerance, so the tie is genuine. The procedure forbids breaking it on vendor, amount, date or ledger order: the line is flagged `AMBIGUOUS_MATCH` with both candidates named in `Candidate_Ledger_IDs`, and both entries are listed. Picking either one costs three graded rows. |
| Traps | Nine; see below. |

## Traps

| Trap | Where | Lazy algorithm it separates |
|---|---|---|
| One statement line settling three invoices | `TXN1438` → `AP0171`, `AP0172`, `AP0173` | 1:1 matching, which cannot represent a payment run and drops the line and all three invoices |
| A genuine duplicate payment | `TXN1820` settles `AP0174`, `TXN2151` repeats it | greedy match-and-forget, which reports the second line as an ordinary no-match and hides that the vendor was paid twice |
| A rounding difference of one penny | 40 settlements, e.g. `TXN0002` at +0.01, plus `TXN1218` at exactly +0.02 and `TXN2152` at 0.05 | exact-amount equality, which rejects every settlement that is not to the penny and cannot place the inclusive bound |
| A reversal pair netting to zero | `TXN2441` (−1,975.60) and `TXN2541` (+1,975.60) against `AP0177` | matching on unsigned amount, which settles the invoice from the debit leg and never notices the money came back |
| A payment to a vendor absent from the ledger | `TXN1546`, Ashcombe Scaffolding Ltd | dropping what does not match, instead of reporting it as `VENDOR_NOT_ON_LEDGER` so someone can chase it |
| Two ledger entries fitting one reference equally well | `TXN2255` against `AP0178` and `AP0179` | pick-the-first, which resolves a tie the procedure says to escalate |
| Zero-padded, unhyphenated and lower-case references | 40 of the clean settlements, e.g. `INV-001019`, `INV1042`, `inv 1030` | raw string equality on the reference field, which sees three different invoices |
| A cancelled ledger entry that would otherwise match exactly | `AP0180` / `TXN2542`, same reference, same amount, one day apart | matching before applying the scope rule, which settles an invoice that was cancelled and never reports the payment |
| Three business days across two bank holidays, and a half-up tie | `TXN0500` (seven calendar days, three business days) and `TXN0824` (−1,204.125 against 1,204.12) | calendar-day or plain-weekday windows, which reject a settlement the procedure accepts; and banker's rounding, which writes 1,204.12 and a difference of 0.00 where the procedure requires 1,204.13 and 0.01 |

## The three implementations

## Ordering and layout requirements, and where each is graded

| Stated in the procedure | Graded by |
|---|---|
| §8.1 three sheets named `Matched`, `UnmatchedBank`, `UnmatchedLedger`, in that order | `artifacts.sheet_and_column_order`, one point per sheet position, paid only when that sheet carries rows |
| §1 and §8.1 column names and column order from `sop/Format_Example.xlsx` | `artifacts.required_columns` (names) and `artifacts.sheet_and_column_order` (position) |
| §8.1 `Matched` and `UnmatchedBank` sorted by `Txn_ID` ascending, `UnmatchedLedger` by `Ledger_ID` ascending | `artifacts.row_order`, the fraction of positions whose key matches the key's own row at that position |
| §5.5 and §8.2 `Ledger_IDs` and `Candidate_Ledger_IDs` ascending, semicolon-separated | `matched` and `unmatched_bank`, which split the cell on the semicolon and compare the sequence in order |
| §6.1 and §7 reason precedence | the `Reason` column of `unmatched_bank` and `unmatched_ledger` |

## Waivers

None. One coverage gap is documented rather than closed: the window's lower bound carries a record on the bound (`AP0181`, due 2026-03-23) and an out-of-window negative three days before it (`AP0183`, due 2026-03-20), but none on 2026-03-22, so an agent that opens the window one day early is caught only by the upper bound. Closing it means inserting a ledger entry, which renumbers every later `Ledger_ID` and rewrites the answer key; the key is verified correct as it stands, so the gap is the cheaper trade.
