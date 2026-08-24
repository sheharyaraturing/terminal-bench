# Metric definitions — Support Contact Coverage

Owner: Customer Operations, metrics stewardship. Applies to the extract shipped alongside this file under `data/`.

## 1. Reporting period

The reporting period for this extract is **2025-04-01 to 2025-06-30**. Both endpoints are **inside** the period: a ticket opened on 2025-04-01 is in period, and so is one opened on 2025-06-30. A ticket opened on 2025-03-31 or on 2025-07-01 is not.

Period membership is decided by the ticket's `opened_at` date and by nothing else. `deleted_at` never moves a ticket into or out of the period.

This extract is a frozen snapshot. The reporting period is the one written above, and it is not derived from today's date.

## 2. The extract

`data/customers.csv` — columns `customer_id`, `customer_name`, `segment`, `region`, `signed_on`. As delivered it holds a header row and **98 data rows**.

`data/tickets.csv` — columns `ticket_id`, `customer_id`, `opened_at`, `channel`, `subject`, `deleted_at`. As delivered it holds a header row and **405 data rows**. A live ticket carries an empty `deleted_at`.

`data/tickets.csv` is larger than a single file-read tool response will return. Read it through the terminal server (`wc -l`, `grep`, `awk`, `sed -n '200,300p'`) or from a script that opens the file directly; do not rely on one dump of the whole file. If your row counts do not match the two figures above, you have not read all of the data and the figure you produce will be wrong.

## 3. The customer population

The population is the set of **distinct `customer_id` values** in `data/customers.csv`. `customers.csv` is an export, not a keyed table, and the same `customer_id` may appear on more than one row. Repeated rows describe one customer, not several: collapse them to a single member of the population before counting anything.

Every population figure in this document — `customers_total`, `customers_with_contact`, the answer row set — is counted over distinct `customer_id` values, never over file rows.

## 4. Ticket classification

Classify every row of `data/tickets.csv` by applying these tests **in this order** and stopping at the first that matches. Each ticket lands in exactly one class.

1. **Out of period** — `opened_at` is before 2025-04-01 or after 2025-06-30. Counted as `out_of_period_tickets`. It is not examined further: an out-of-period ticket is never an orphan and never a soft-delete, whatever its other fields say.
2. **Orphan** — `customer_id` is empty, or its value does not match any `customer_id` in `data/customers.csv`. Counted as `orphan_tickets`. An orphan is discarded even when `deleted_at` is empty, and it is counted as an orphan even when `deleted_at` is set.
3. **Soft-deleted** — `deleted_at` is non-empty. Counted as `soft_deleted_tickets`. A soft-deleted ticket is **not contact**: it is treated exactly as if the ticket had never been raised.
4. **Contact** — everything else. The ticket is a qualifying contact for the customer named by its `customer_id`.

An empty `customer_id` is a missing value, not a customer identifier and not a zero. It matches no `customer_id` in `data/customers.csv`, and it classifies under test 2 above like any other unmatched value.

## 5. The metric

A customer **has contact** when at least one ticket in class 4 above names that customer. A customer is **without contact** when no ticket in class 4 names it — including a customer that has tickets in classes 1, 2 or 3 only, and a customer with no ticket rows at all.

- `customers_total` — distinct `customer_id` values in `data/customers.csv`.
- `customers_with_contact` — distinct customers in the population with at least one class-4 ticket. Ticket `customer_id` values that are not in the population never contribute to this figure.
- `value` — distinct customers in the population without contact. `customers_with_contact + value` must equal `customers_total`.
- `contact_rate` — `customers_with_contact / customers_total`.

## 6. Rounding

`contact_rate` is recorded to **four decimal places, rounded half-up**: a digit sequence sitting exactly halfway rounds away from zero, so 0.61255 becomes 0.6126. Banker's rounding — which most default `round()` implementations use, and which sends an exact half to the nearest even digit — is **not** the convention here and will differ from this specification in the fourth decimal place. No other figure in this metric is rounded; the rest are exact integer counts.

## 7. Undefined values and reason codes

Where a customer's attribute cannot be established from the extract, record the sentinel string `UNDETERMINED` in that cell and the matching reason code in `data_issue`. Do not guess, do not leave the cell empty, do not write `0`, `null`, `N/A` or a blank string, and do not drop the row.

| Situation | Cell that becomes `UNDETERMINED` | `data_issue` |
|---|---|---|
| The customer's `customer_id` appears on more than one row of `customers.csv` and those rows do not agree on `customer_name` | `customer_name` | `AMBIGUOUS_NAME` |
| The customer's `segment` is empty | `segment` | `MISSING_SEGMENT` |
| Neither of the above | — | `NONE` |

Repeated rows that agree on every field are the same record twice: collapse them silently, with `data_issue` of `NONE`. A conflict is a disagreement in the field's value, not the mere presence of a repeat.

`AMBIGUOUS_NAME` takes precedence if a row somehow qualifies for both codes. `data_issue` is never empty — write `NONE` where there is no issue.

## 8. Output — `no_contact.xlsx`

Write `no_contact.xlsx` to the workspace root. It carries a sheet named exactly `NoContact` whose first row is the header and whose columns are, in this order:

| Column | Contents |
|---|---|
| `customer_id` | the customer identifier |
| `customer_name` | `customer_name` from `customers.csv`, or `UNDETERMINED` |
| `segment` | `segment` from `customers.csv`, or `UNDETERMINED` |
| `data_issue` | `AMBIGUOUS_NAME`, `MISSING_SEGMENT` or `NONE` |

`metrics/Format_Example.xlsx` carries this sheet and header row and no data rows; it is the authority on spelling, capitalisation and column order.

One row per customer without contact, and no other rows. Sort ascending by `customer_id`. Customers that have contact do not appear, and no customer appears twice.

Record **computed values, not formulas**. Every cell must hold a literal string or number; a cell holding an Excel formula is not an answer.

## 9. Output — `workings.json`

Write `workings.json` to the workspace root, a single JSON object with exactly these ten keys:

```json
{
  "metric": "customers_without_contact",
  "period_start": "2025-04-01",
  "period_end": "2025-06-30",
  "customers_total": 0,
  "customers_with_contact": 0,
  "value": 0,
  "contact_rate": 0.0,
  "orphan_tickets": 0,
  "soft_deleted_tickets": 0,
  "out_of_period_tickets": 0
}
```

`metric`, `period_start` and `period_end` are the literal strings shown. The three ticket counts are the class totals from section 4, over the whole of `data/tickets.csv`. The zeros above are placeholders for shape only — every count must be the figure you derived, and the workings are part of the deliverable, not an optional extra. A submission that reports `value` without the ticket-class counts is incomplete.
