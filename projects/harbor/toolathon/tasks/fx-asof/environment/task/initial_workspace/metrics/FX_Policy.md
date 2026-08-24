# Group FX Reporting Policy -- USD restatement

Owner: Group Financial Control. Applies to every pack that restates trading-currency revenue into
the group reporting currency.

## 1. Reporting currency and period

The group reporting currency is **USD**.

- Reporting period: **2023-04-01** to **2023-06-30**, both dates inclusive.
- A transaction belongs to the period when its `txn_date` falls on or between those two dates. A
  transaction dated one day either side is out of scope, whatever posting run carried it.

## 2. Population

`transactions.csv` is the trading record. It holds 96 rows; only a subset of them enters the
restatement. A transaction enters the restatement when **both** hold:

1. its `txn_date` is inside the reporting period, and
2. its `status` is `posted`.

Records with any other status never enter the restatement, are counted in none of its figures, and
are not reported as undefined either. They are simply outside the population.

## 3. The rate that applies

- Authoritative snapshot: `reference/fx_rates.csv`, published by the group's rate vendor and frozen
  for the period. Every figure in this restatement is struck from it and from nothing else: a rate
  is usable here only if it carries a `quote_date`, and only if it came out of that file.
- The snapshot quotes `usd_per_unit`: the USD received for **one unit** of the quoted currency.
  Convert by multiplying, `usd_amount = amount * usd_per_unit`.
- The applicable rate is the one published **on the transaction's own date**. Not period-end, not
  the latest rate in the snapshot, not an average over the period.
- Rates are published only on days the vendor's fixing calendar is open. Weekends and public
  holidays carry no publication.
- **Carry forward.** Where nothing is published on the transaction's date, use the most recent rate
  published *strictly before* it, however many days back that reaches. Record the date of the quote
  actually used, not the transaction date.
- **Interpolation is forbidden.** Never average, blend or straight-line between the quotes either
  side of a gap.
- **Never carry a rate backwards.** A quote published after the transaction date is not available to
  that transaction, however close it sits.
- Coverage does not begin on the same date for every currency.
- Rates are published to eight decimal places. Use the published figure as it stands; do not
  re-round it before converting.

### 3.1 Transactions already in USD

A transaction whose currency is already `USD` is in the reporting currency. Carry the amount
through unchanged. Do not look a rate up for it, do not let any calendar gap affect it, and never
count it as a carried-forward conversion. Record its `Rate` as `1.00000000`, its `Rate_Date` as the
transaction's own date, and its `Rate_Basis` as `NOT_APPLICABLE`.

### 3.2 Redenominations

When a currency is redenominated the snapshot keeps the same three-letter code and the published
series steps to the new scale on the redenomination date. Each transaction still takes the rate
published on its own date. Do not restate transactions dated before the step at the post-step
scale, and do not apply one rate across the break.

## 4. Undefined

A conversion the snapshot cannot support is **undefined**. Undefined is not zero, not blank and not
omitted, and no proxy may be substituted -- not a related currency, not a peg, not another vendor's
rate, not an estimate.

Where a conversion is undefined, write the literal string `UNDEFINED` in `Rate_Date`, `Rate` and
`USD_Amount`, and record which of the two reasons applies in `Rate_Basis`:

| `Rate_Basis` | When it applies |
|---|---|
| `NO_RATE_FOR_CURRENCY` | the snapshot carries no row at all for the transaction's currency |
| `NO_RATE_ON_OR_BEFORE_DATE` | the snapshot carries the currency but publishes nothing dated on or before the transaction date |

Undefined transactions stay in the population. They appear as rows in the workbook and they are
counted in `transactions_by_currency`. They contribute nothing to `total_usd_revenue` and they are
never counted as carried forward.

## 5. Rounding

- Convert in exact decimal arithmetic. Binary floating point lands on the wrong side of a half cent
  and this policy is written to the cent.
- Round each converted amount to **two decimal places, half-up**: a value sitting exactly on the
  half cent rounds away from zero, so `2183.865` becomes `2183.87` and never `2183.86`.
- Round per transaction first, then add the rounded amounts to reach the period total. Do not total
  the unrounded products.

## 6. Rate basis

Every row records how its rate was obtained:

| `Rate_Basis` | Meaning |
|---|---|
| `PUBLISHED` | the snapshot publishes this currency on the transaction date |
| `CARRIED_FORWARD` | nothing was published that date; the most recent earlier quote was used |
| `NOT_APPLICABLE` | the transaction is already in USD, per section 3.1 |
| `NO_RATE_FOR_CURRENCY` | undefined, per section 4 |
| `NO_RATE_ON_OR_BEFORE_DATE` | undefined, per section 4 |

## 7. Deliverables

### 7.1 `usd_revenue.xlsx`

One workbook in the workspace root holding a sheet named **`USD_Revenue`**, whose first row is the
header and whose columns are, in this order:

`Txn_ID`, `Currency`, `Amount`, `Rate_Date`, `Rate`, `USD_Amount`, `Rate_Basis`

One row per transaction in the population, ordered by `Txn_ID` ascending. The sheet name, the
column order and the row order are all part of the deliverable and are checked as stated.
`Rate_Date` is an ISO `YYYY-MM-DD` string. `Amount` and `USD_Amount` carry two decimals; `Rate` is
reproduced as published.

`metrics/Format_Example.xlsx` fixes the layout: the sheet name, the header text, the column order
and the shape of each cell. It is a layout sample, not an extract of the trading record.

**Record computed values, not formulas.** A workbook written outside Excel carries no cached
result, so a formula reads as empty to everything downstream. Write the numbers.

### 7.2 `workings.json`

One JSON object in the workspace root, with exactly these keys:

```json
{
  "metric": "usd_revenue",
  "period_start": "2023-04-01",
  "period_end": "2023-06-30",
  "total_usd_revenue": 0.00,
  "transactions_by_currency": {"EUR": 0},
  "carried_forward_count": 0,
  "undefined_count": 0,
  "undefined_by_reason": {"NO_RATE_FOR_CURRENCY": 0, "NO_RATE_ON_OR_BEFORE_DATE": 0}
}
```

- `total_usd_revenue` -- the sum of the rounded `USD_Amount` values, to two decimals.
- `transactions_by_currency` -- one key per currency that appears in the population, holding the
  count of population transactions in that currency. USD-denominated and undefined transactions are
  counted here like any other. A currency with no transaction in the population gets no key.
- `carried_forward_count` -- how many rows carry a `Rate_Basis` of `CARRIED_FORWARD`.
- `undefined_count` -- how many rows are undefined.
- `undefined_by_reason` -- both reason codes are always present, carrying `0` where none occurred.

## 8. Working with the snapshot

`reference/fx_rates.csv` covers sixteen currencies over three calendar years and runs to several
hundred kilobytes. Reading it whole through a single tool call will be truncated long before the
end. Filter it instead -- `grep` a currency code, `awk` a date range, or read it with the `csv`
module from a script -- and satisfy yourself that the row you used really is the latest one dated on
or before the date you needed.
