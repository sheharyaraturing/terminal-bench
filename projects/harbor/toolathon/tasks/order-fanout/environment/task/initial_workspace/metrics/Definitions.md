# Revenue by customer — metric definition

Owner: Revenue Operations · Status: **in force** · Supersedes: RD-2023-04

This document is the sole authority for how revenue by customer is computed. Anything not
stated here is not part of the metric.

## 1. Reporting period

The reporting period is the September 2024 quarter: `order_date` between `2024-07-01` and
`2024-09-30`, **both dates included**. An order dated `2024-07-01` is inside the period and an
order dated `2024-09-30` is inside the period; `2024-06-30` and `2024-10-01` are outside it.

The period never moves. Do not resolve it against the current date.

## 2. Source extracts

| File | Grain | Notes |
|---|---|---|
| `data/customers.csv` | one row per customer | `account_type` is `standard`, `enterprise` or `internal` |
| `data/orders.csv` | one row per order | 38 rows; `order_total` is recorded to three decimal places |
| `data/order_lines.csv` | one row per order line | the largest extract; `line_amount` is a cost allocation posted per SKU |
| `data/shipments.csv` | one row per shipment leg | carrier, parcel count and weight; the extract carries no monetary column |

The table gives each extract's grain and nothing more. Which of them can carry revenue is
settled by §4, not by this table: an extract that holds no amount at order grain cannot be a
source for this metric, whatever else it records about the order.

`data/order_lines.csv` is longer than one file read returns — a single read of it comes back
truncated. Read it in ranges or filter it (`wc -l`, `grep`, `awk`, `sed -n '1,60p'` through the
terminal server, or repeated ranged reads) rather than in one call, and confirm the row count
you worked from against `wc -l` before you rely on it.

## 3. Population

Start from every row of `data/orders.csv`. An order is excluded when one of the following
applies. Test them **in this order** and count each excluded order under the **first** reason
that matches, so that the three reasons partition the excluded rows exactly once each:

1. `internal_account` — the order's customer has `account_type` = `internal` in
   `data/customers.csv`. Internal accounts are staff and demo accounts; their orders never
   count, whatever their date or status.
2. `out_of_period` — `order_date` falls outside the period in §1.
3. `cancelled_or_draft` — `status` is `cancelled` or `draft`.

Every order surviving all three tests is **in scope**. The statuses `confirmed`, `shipped`
and `delivered` are all in scope; no other status appears in the extract.

`included` plus the three excluded counts must equal the 38 rows of
`data/orders.csv`. If it does not, rows have been double-counted or dropped.

## 4. The measure

Revenue comes from `orders.order_total` and from nowhere else. The order total is
authoritative.

`order_lines.line_amount` allocates an order across SKUs for cost reporting. It does **not**
reconcile to the order total: allocations are posted late, some lines carry no amount at all,
and an order may have no lines against it. Never derive revenue by summing line amounts, and
never let the number of lines an order carries change the amount that order contributes.

**Each in-scope order contributes its `order_total` exactly once**, to exactly one customer.

An order whose `order_total` is `0.000` is a real order that earned nothing. It is in scope,
it counts towards that customer's order count, and it contributes `0.00` to their revenue. It
is not the same thing as a customer having no orders.

## 5. Currency

Each order is denominated in `orders.currency`. Currencies are never converted and never
added together.

- When every in-scope order for a customer carries the same currency, that is the customer's
  currency and their revenue is the sum of those order totals.
- When a customer's in-scope orders carry **more than one** currency, that customer's revenue
  is **undefined**. Report the sentinel `UNDEFINED` — upper case, exactly that spelling — in
  both the `Currency` and the `Revenue` cell, and `mixed_currency` in `Undefined_Reason`. Do not
  sum across the currencies, do not convert, do not fall back to the majority currency, do
  not split the customer across two rows, and do not drop the customer.

The reporting currency is **USD**.

## 6. Rounding

Revenue is reported to two decimal places using **half-up** rounding: a half-cent rounds away
from zero, so `0.005` becomes `0.01` and `10.125` becomes `10.13`. Python's built-in
`round()` and `format()` round half to even and will disagree in the cent;
`Decimal(...).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)` is the intended mode.

Round **once**, at the point of reporting: add the unrounded order totals first, then round
the customer's revenue. That rule fixes each customer's `Revenue` cell and nothing else; the
`value` key in §8 is defined over those already-rounded cells, not over the order totals
again.

## 7. Output — `revenue_by_customer.xlsx`

Write `revenue_by_customer.xlsx` in the workspace root, with a sheet named `Revenue`.
`metrics/Format_Example.xlsx` carries the header row and nothing else; the columns, in this
order:

| Column | Contents |
|---|---|
| `Customer_ID` | the customer's id |
| `Customer_Name` | `customer_name` from `data/customers.csv`, copied exactly |
| `Currency` | the customer's single currency, or `UNDEFINED` |
| `Orders` | how many in-scope orders the customer has, counted at order grain |
| `Revenue` | the customer's revenue rounded per §6, or `UNDEFINED` |
| `Undefined_Reason` | `mixed_currency` where revenue is undefined; left blank otherwise |

One row per customer that has **at least one in-scope order**. A customer with no in-scope
order does not appear at all — not as a zero row, not as a blank row. Rows are ordered by
`Customer_ID` ascending.

**Record values, not formulas.** Every cell holds the computed value. A cell holding
`=SUM(...)` reads back as empty to the reader that consumes this file, and is scored as a
blank.

## 8. Output — `workings.json`

Write `workings.json` in the workspace root. The shape is fixed; every key below is required
and no key may be omitted, even when its value is `null`:

```json
{
  "metric": "revenue_by_customer",
  "value": 0.0,
  "undefined": false,
  "undefined_reason": null,
  "denominator": null,
  "population": {
    "included": 0,
    "excluded": {
      "internal_account": 0,
      "out_of_period": 0,
      "cancelled_or_draft": 0
    },
    "rows_before_join": 0,
    "rows_after_join": 0
  }
}
```

| Key | Value |
|---|---|
| `metric` | the string `revenue_by_customer` |
| `value` | total revenue in the reporting currency: add up the `Revenue` cells **exactly as §7 reports them**, for the rows whose `Currency` is `USD`. Those cells are already rounded per §6, and their sum needs no further rounding. Do not re-derive this figure by summing the unrounded order totals and rounding once at the end — that is a different number here. Rows in any other currency, and rows reported `UNDEFINED`, are not added in. A JSON number, not a string |
| `undefined` | a JSON boolean. `true` only when no in-scope order is denominated in `USD`, in which case `value` is `null` and `undefined_reason` is `no_reporting_currency_orders`. Otherwise `false` |
| `undefined_reason` | `null` when `undefined` is `false`; the reason code otherwise |
| `denominator` | `null`. Revenue is a total, not a rate, so it has no denominator — but the key is still required |
| `population.included` | the number of in-scope orders from §3 |
| `population.excluded` | the three counts from §3, under exactly those three keys |
| `population.rows_before_join` | the number of order rows in scope, at order grain, before any join to `data/order_lines.csv` |
| `population.rows_after_join` | the number of rows an inner join of those in-scope orders to `data/order_lines.csv` on `order_id` produces — equivalently, how many `order_lines` rows belong to an in-scope order. An in-scope order carrying no lines contributes one row to `rows_before_join` and none to `rows_after_join`; an order carrying four lines contributes one and four |

Both counts are reported whether or not they agree.
