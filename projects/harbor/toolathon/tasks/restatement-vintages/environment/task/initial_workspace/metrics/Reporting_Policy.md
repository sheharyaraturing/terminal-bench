# Restatement Reporting Policy — v4

Effective 2025-11-20. This policy supersedes Close Memo 2025-08 (`metrics/Close_Memo.docx`) in full.

## Contents

1. The filing register
2. The reporting cutoff
3. Which periods the pack covers
4. Publishable filings and selectable vintages
5. Choosing the two vintages
6. When a period is undefined
7. The revision percentage
8. Record accounting
9. Output — `vintage_report.xlsx`
10. Output — `workings.json`

Each section is a `##` heading, so `grep -n '^## ' metrics/Reporting_Policy.md` gives you the line numbers to page to.

## 1. The filing register

`financials.csv` is bitemporal. Each row is one filing of one figure: the period the figure describes, and the date that figure was filed. A period therefore carries several rows, one per vintage, and the same figure is restated as often as the facts change.

| Column | Meaning |
|---|---|
| `record_id` | filing identifier, unique |
| `reported_for_period` | the fiscal quarter the figure describes |
| `as_of_date` | the date the figure was filed — the vintage date |
| `basis` | `statutory` or `management` |
| `vintage_type` | `preliminary`, `final` or `restated` |
| `net_revenue_usd` | the filed figure, whole US dollars |
| `filing_note` | the filer's own commentary, keyed in free-hand rather than chosen from a controlled list |

An empty `net_revenue_usd` cell means the filing was registered but no figure was published. It is not a zero and it is not a figure of any kind.

## 2. The reporting cutoff

The reporting cutoff for this round is **2025-11-14**.

A filing whose `as_of_date` is on or before the cutoff is within the round. A filing whose `as_of_date` is strictly after the cutoff is outside it and takes no part in any figure the pack reports. The bound is inclusive: `as_of_date <= 2025-11-14`.

The cutoff is a property of the round and is fixed at the value stated above. It is not derived from the current date, from the latest filing in the register, or from any period end.

## 3. Which periods the pack covers

`close_calendar.csv` lists every fiscal period the entity recognises, each with a `close_status` of `closed`, `open` or `under_review`.

The pack covers exactly the periods whose `close_status` is `closed` — one row per such period and no row for any other period, whether or not the register carries filings for it. Rows are written in ascending period order.

## 4. Publishable filings and selectable vintages

A filing is **publishable** when all three of the following hold:

- its `basis` is `statutory`. The management basis is an internal parallel ledger kept on a different segment tree; it never enters the pack, and a management filing does not become publishable by being the most recent thing on file.
- its `vintage_type` is `final` or `restated`. A `preliminary` filing is an unaudited flash estimate. It is never publishable, however late it was filed and however many times it was revised.
- its `net_revenue_usd` cell is non-empty.

A publishable filing is a **selectable vintage** for its period when, in addition, its `reported_for_period` is a period the pack covers (section 3) and its `as_of_date` is within the round (section 2).

Within one period, no two selectable vintages carry the same `as_of_date`.

## 5. Choosing the two vintages

For each period the pack covers, over that period's selectable vintages and no others:

- the **latest vintage** is the one with the greatest `as_of_date`;
- the **original vintage** is the one with the least `as_of_date`.

Both are chosen inside the period. A vintage filed for one period never stands in for another, and the greatest `as_of_date` in the register as a whole is not the latest vintage of any particular period.

Where a period has exactly one selectable vintage, that vintage serves as both the latest and the original.

`Latest_Amount_USD` and `Latest_Vintage_Date` are the amount and `as_of_date` of the latest vintage; `Original_Amount_USD` and `Original_Vintage_Date` are the amount and `as_of_date` of the original vintage. Both columns carry the figures as filed. A restatement may move a figure in either direction and the pack reports what was filed, not what was expected.

## 6. When a period is undefined

Some covered periods cannot be reported. The row is still written, every value column carries the literal `UNDEFINED`, and `Undefined_Reason` carries one of three codes. Test them in this order and use the first that applies.

| Order | Code | Applies when |
|---|---|---|
| 1 | `no_records` | the register holds no row at all for the period |
| 2 | `no_reportable_vintage` | the period has rows, but none of them is publishable — irrespective of date |
| 3 | `all_vintages_after_cutoff` | the period has publishable filings, but every one of them falls outside the round |

`UNDEFINED` is the exact spelling and the only accepted sentinel. A blank cell, `0`, `N/A`, `null`, `-` and an omitted row are each wrong and are each read as a failure to answer. A period whose only figures are preliminary is `UNDEFINED`; a preliminary figure is never promoted to fill the gap.

Where a period is reportable, `Undefined_Reason` carries the literal `NONE`, not a blank cell.

## 7. The revision percentage

`Revision_Pct` = (`Latest_Amount_USD` − `Original_Amount_USD`) ÷ `Original_Amount_USD` × 100.

Round **half-up to one decimal place**: a value whose next digit is exactly 5 rounds away from zero, so 2.25 becomes 2.3 and −2.25 becomes −2.3. Half-to-even — which is what most language runtimes give you by default, and what the superseded memo used — is not the mode here. Round once, at the end.

Where the period is `UNDEFINED`, `Revision_Pct` is `UNDEFINED`. Where the latest and original vintages are the same filing, `Revision_Pct` is `0.0`, which is a reported figure and not a blank.

## 8. Record accounting

Every row of `financials.csv` lands in exactly one bucket. Test the buckets in this order and count the row against the first that applies, so that the six counts sum to the row count of the register.

| Order | Bucket | Applies when |
|---|---|---|
| 1 | `out_of_scope_period` | the row's period is not `closed` in `close_calendar.csv` |
| 2 | `management_basis` | `basis` is not `statutory` |
| 3 | `after_cutoff` | `as_of_date` is after the cutoff |
| 4 | `no_amount` | `net_revenue_usd` is empty |
| 5 | `preliminary` | `vintage_type` is `preliminary` |
| — | `included` | everything else — the selectable vintages |

A row that satisfies more than one test is counted only against the earliest of them.

## 9. Output — `vintage_report.xlsx`

Written to the workspace root, with one sheet named `Vintage_Report`. Seven columns, in this order:

`Period`, `Latest_Amount_USD`, `Latest_Vintage_Date`, `Original_Amount_USD`, `Original_Vintage_Date`, `Revision_Pct`, `Undefined_Reason`

- `Period` — spelled as in `close_calendar.csv`.
- The two amount columns — whole US dollars as a number: no currency symbol, no thousands separator, no decimal part.
- The two vintage date columns — in `YYYY-MM-DD`.
- `Revision_Pct` — a number to one decimal place per section 7. Not a percentage string, not a fraction.
- `Undefined_Reason` — a code from section 6, or the literal `NONE`.
- Rows — one per covered period, in ascending period order (section 3).

`metrics/Format_Example.xlsx` carries the header row and two rows in exactly this shape, under the period labels `EXAMPLE-A` and `EXAMPLE-B`.

**Record computed values, not formulas.** Every cell holds a result. A cell holding `=B2-C2` reports a formula rather than a figure, and the figure counts as not reported.

## 10. Output — `workings.json`

Written to the workspace root, in exactly this shape:

```json
{
  "metric": "statutory_net_revenue_usd",
  "reporting_cutoff": "2025-11-14",
  "value": 0,
  "undefined": false,
  "undefined_reason": null,
  "denominator": null,
  "periods_defined": 0,
  "periods_undefined": 0,
  "population": {
    "included": 0,
    "excluded": {
      "out_of_scope_period": 0,
      "management_basis": 0,
      "after_cutoff": 0,
      "no_amount": 0,
      "preliminary": 0
    }
  }
}
```

Every number above is a placeholder. The keys, their spelling and their nesting are the contract.

- `metric` and `reporting_cutoff` are the two constants shown.
- `value` — the sum of `Latest_Amount_USD` across the covered periods that are reportable, as a whole number. Undefined periods contribute nothing to it.
- `undefined` is `false` and `undefined_reason` is `null` for this pack: the metric as a whole is defined even where individual periods are not. `denominator` is `null`; this metric has no denominator.
- `periods_defined` and `periods_undefined` — counts of sheet rows of each kind. They sum to the number of covered periods.
- `population.included` and the five `excluded` counts — section 8.
