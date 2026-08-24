# GROUND_TRUTH.md — journal-balance-forensics

Everything below was read **back out of the built artefacts** by the read-back
stage of `build_fixture.sh` (`bash build_fixture.sh` regenerates this file). The
journal was re-parsed from `journal.jsonl` line by line; the period-close facts
were obtained by executing `extra.sql` into a scratch SQLite database and
querying it back. No value here comes from the builder's in-memory state.

## Shape

- `journal.jsonl` lines: **400**
- distinct entries: **140** (`JE-0001` .. `JE-0140`)
- fields per line: `entry_id`, `line_no`, `account`, `account_name`, `debit`, `credit`, `currency`, `period`, `posted_at`, `memo`, `source`
- lines per period: 2024-04 73, 2024-05 72, 2024-06 65, 2024-07 71, 2024-08 57, 2024-09 62
- lines per currency: EUR 39, GBP 48, USD 313
- distinct accounts used: **14**
- `gl_period_close` rows: **9** (2024-01, 2024-02, 2024-03, 2024-04, 2024-05, 2024-06, 2024-07, 2024-08, 2024-09)

## Layer 1 — entries whose debits do not equal their credits

count: **5**

| entry | period | currency | debits | credits | debits - credits |
|---|---|---|---:|---:|---:|
| `JE-0018` | 2024-04 | USD | 12,400.00 | 12,040.00 | 360.00 |
| `JE-0047` | 2024-05 | USD | 8,750.00 | 8,750.50 | -0.50 |
| `JE-0073` | 2024-06 | USD | 45,000.00 | 4,500.00 | 40,500.00 |
| `JE-0098` | 2024-07 | GBP | 3,215.75 | 3,251.75 | -36.00 |
| `JE-0121` | 2024-08 | USD | 19,880.00 | 21,000.00 | -1,120.00 |

- signed total of the five differences: **39,703.50**
- sum of absolute differences: **42,016.50**
- largest single imbalance: `JE-0073` at **40,500.00** (debits 45,000.00 vs credits 4,500.00 — a one-decimal-place shift on the credit side)

- whole-file totals: debits 3,828,680.79, credits 3,788,977.29, difference 39,703.50
- with those five entries excluded: debits **3,739,435.04**, credits **3,739,435.04**, difference **0.00** — the rest of the ledger foots exactly

## Decoy — the entry that is balanced at zero

entries in which every line is 0.00 / 0.00: **1** — `JE-0055`

- `JE-0055`: 2 lines, period 2024-05, accounts 1600, 2100
  - memo: "Placeholder - annual broker insurance accrual, amount pending confirmation"
  - debits 0.00 = credits 0.00, so it **balances** and is NOT one of the 5 imbalances above

## Layer 2a — postings dated outside their own period

entries whose `posted_at` month differs from `period`: **6**

| entry | period | posted_at | period close_date | status | after close? |
|---|---|---|---|---|---|
| `JE-0029` | 2024-04 | 2024-05-02 | 2024-05-08 | CLOSED | no |
| `JE-0058` | 2024-05 | 2024-06-03 | 2024-06-07 | CLOSED | no |
| `JE-0064` | 2024-05 | 2024-06-19 | 2024-06-07 | CLOSED | **YES** |
| `JE-0082` | 2024-06 | 2024-07-05 | 2024-07-05 | CLOSED | no |
| `JE-0091` | 2024-07 | 2024-08-01 | 2024-08-06 | CLOSED | no |
| `JE-0112` | 2024-07 | 2024-08-05 | 2024-08-06 | CLOSED | no |

entries posted strictly after their period's close date: **1**

- **`JE-0064`** — period **2024-05** (status `CLOSED`, closed **2024-06-07**), posted **2024-06-19**, i.e. **12 days after the close**
  - it BALANCES: debits 26,750.00 = credits 26,750.00, amount **26,750.00** USD
  - accounts 5400 Facilities Expense, 2010 Accounts Payable
  - memo: "May sublease charge omitted from the accrual run"
  - it is invisible to a debits-vs-credits test; the close date lives only in
    `gl_period_close`, not in the journal file

- NEAR-MISS `JE-0082` — period 2024-06, closed 2024-07-05, posted 2024-07-05: posted **on** the
  close date, not after it. The books were still open that day, so it is
  legitimate and must NOT be reported. Amount 14,200.00 USD.

## Layer 2b — reversal pairs

lines whose memo declares a reversal resolve to **6** original/reversal pairs.

| original | ccy | reversal | ccy | amount | currencies match? |
|---|---|---|---|---:|---|
| `JE-0024` | USD | `JE-0035` | USD | 7,325.00 | yes |
| `JE-0041` | GBP | `JE-0052` | GBP | 2,140.60 | yes |
| `JE-0079` | EUR | `JE-0106` | USD | 18,450.00 | **NO** |
| `JE-0088` | USD | `JE-0095` | USD | 5,610.00 | yes |
| `JE-0109` | EUR | `JE-0117` | EUR | 9,880.00 | yes |
| `JE-0131` | USD | `JE-0138` | USD | 15,300.00 | yes |

- **`JE-0079` / `JE-0106` does not offset.** The original is denominated in **EUR**, the reversal in **USD**, both for **18,450.00**.
  - `JE-0079`: 2024-06, debit 5210 Professional Fees 18,450.00 EUR / credit 2010 Accounts Payable 18,450.00 EUR
  - `JE-0106`: 2024-07, debit 2010 Accounts Payable 18,450.00 USD / credit 5210 Professional Fees 18,450.00 USD
  - memo on the reversal: "Reversal of JE-0079 - Q2 statutory audit fee - Hansen & Roth GmbH"
  - **both entries balance internally**, so no entry-level debits-vs-credits test can see this.
  - net effect: 18,450.00 EUR of expense is still on the books while 18,450.00 USD of expense was removed that had never been posted.

## Layer 2b (second defect) — reversal booked to the wrong account

reversals whose currency and amount match the original but whose accounts do not mirror it: **1**

- **`JE-0138` does not offset `JE-0131`.** Same currency (USD) and same amount (15,300.00), and both balance internally, so a currency check, an amount check and an entry-level footing check all pass.
  - `JE-0131` debited **6100 Depreciation Expense** and credited 2100.
  - a correct reversal would credit **6100**; `JE-0138` credits **5400 Facilities Expense** instead, debiting 2100.
  - net effect: the 15,300.00 USD charge on account 6100 is never reversed, and 15,300.00 USD is wrongly credited to account 5400.

### Per-account, per-currency net for the affected expense account

account **5210 Professional Fees** is touched by exactly **2** entries in the whole file:

| currency | debits | credits | net |
|---|---:|---:|---:|
| EUR | 18,450.00 | 0.00 | 18,450.00 |
| USD | 0.00 | 18,450.00 | -18,450.00 |

- EUR: net **18,450.00**
- USD: net **-18,450.00**

## Numbers that appear in no claim

The filler entries are ordinary balanced postings drawn from a seeded stream.
Their individual amounts are deliberately not asserted anywhere; only the
aggregates above are.
