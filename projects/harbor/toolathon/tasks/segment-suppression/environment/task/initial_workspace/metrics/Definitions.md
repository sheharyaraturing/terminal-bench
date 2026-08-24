# Conversion metrics — definitions

Owner: Measurement Standards group. This document is the authority for the `conversion_rate_by_segment` metric. Where a figure produced by any dashboard, extract or query disagrees with this document, this document wins.

## 1. Reporting period

The reporting period for this cycle runs from **2026-02-01 to 2026-02-28**, and **both endpoints are inside the period**. A visit dated 2026-02-01 is in. A visit dated 2026-02-28 is in. A visit dated 2026-01-31 or 2026-03-01 is out, and no proximity to an endpoint changes that.

The period is fixed by this document. It is not derived from the current date, from the newest row in the extract, or from the range of dates the extract happens to contain.

## 2. Source records

Two extracts under `data/`:

| File | Grain | Notes |
|---|---|---|
| `segments.csv` | one row per segment | the dimension table: `segment_id`, `segment_name`, `region`, `launched_on` |
| `events.csv` | one row per exported visit | `visit_id`, `segment_id`, `visit_date`, `channel`, `status`, `outcome` |

`segments.csv` is the register this group maintains: a segment is given a row in it on the day the segment is approved, and `launched_on` on that row records that date. `events.csv` is written by the delivery pipeline, one row per exported visit, and carries whatever `segment_id` string the pipeline stamped on the request at the time it was served — including tags raised for unapproved experiments and tags left over from decommissioned routing rules.

`events.csv` runs to several hundred rows and is larger than a single tool response can return whole. Do not read it as one blob and do not reason from the first page of it. Filter and aggregate it at the shell — `rg`, `awk`, `sort`, `uniq -c`, or a short script over the file — so that every row is counted exactly once.

Column values seen in this extract:

- `channel` — `organic`, `paid`, `email`, `partner`, `internal`
- `status` — `counted`, `void`
- `outcome` — `converted`, `no_convert`, or empty

An empty `outcome` means the visit's result was never written back. It does not mean the visit did not convert, and it does not mean the visit did not happen.

## 3. Eligible visits

A row of `events.csv` is an **eligible visit** when all five of these hold:

1. its `visit_id` has not already appeared on an earlier row of the file;
2. its `segment_id` appears in `segments.csv`;
3. its `visit_date` falls inside the reporting period, endpoints included;
4. its `channel` is not `internal`;
5. its `status` is `counted`.

Every other row is ineligible and contributes to nothing — not to a denominator, not to a numerator, not to the total row.

Notes on each test, because each of them has been got wrong before:

- **Replayed rows.** The export replays a row when a batch is re-sent. A replayed row repeats a `visit_id` already present. The first occurrence of a `visit_id` is the visit; every later occurrence of that same `visit_id` is a replay and is dropped.
- **Unregistered segments.** A `segment_id` in `events.csv` that is absent from `segments.csv` is an unregistered segment. Its rows are dropped and it does **not** get a row of its own in the output.
- **Internal traffic.** `channel = internal` is staff and QA traffic. It is not customer traffic and it never counts.
- **Voided rows.** `status = void` marks a row the bot filter rejected after the fact. It is not a visit.

A segment listed in `segments.csv` is reported whether or not it has any eligible visits, and whether or not it appears in `events.csv` at all.

## 4. Exclusion accounting

Every ineligible row is attributed to **exactly one** reason. Where a row fails more than one test, the first reason in this order takes it and the others are not counted:

1. `duplicate_visit_id`
2. `unknown_segment`
3. `outside_period`
4. `internal_channel`
5. `void_status`

So a row that is both `internal` and `void` counts once, under `internal_channel`. A replay of a voided row counts under `duplicate_visit_id`, while the voided original counts under `void_status`.

The accounting must balance: rows read from `events.csv` (excluding its header) equals eligible visits plus the five exclusion counts.

## 5. Numerator and denominator

For each segment in `segments.csv`:

- **Denominator** — the number of eligible visits carrying that `segment_id`.
- **Numerator** — the number of those eligible visits whose `outcome` is `converted`.

An eligible visit with an empty `outcome` is **in the denominator and not in the numerator**. It is a visit that happened; only its result is missing. Dropping such visits from the denominator overstates the rate and is wrong.

Both figures are reported for every segment, always, as whole numbers — including when they are `0`, and including for segments whose rate is suppressed under section 7. Suppression applies to the rate, never to the counts.

## 6. Rate and rounding

    Rate = (Numerator / Denominator) * 100

expressed as a percentage and rounded to **two decimal places, half-up**: a value exactly halfway between two representable results rounds away from zero. `4.125` becomes `4.13`, not `4.12`. Banker's rounding (round-half-to-even), which is what most default rounding helpers do, is **not** the convention here and will differ from this document in the second decimal place.

Round once, at the end, from the exact ratio. Do not round the ratio first and scale afterwards.

A rate of `0.00` is a real, publishable figure. A segment with a sufficient denominator and no conversions has a conversion rate of `0.00`, and that is what is reported for it.

## 7. Suppression and the undefined sentinel

A rate is published only when the segment's denominator is **30 or more**. Thirty is inside the publishable range: a denominator of exactly 30 is published.

Where the rate is not published it is **undefined**, and undefined has two distinct causes that are reported differently:

| Condition | `Rate` cell | `ReasonCode` |
|---|---|---|
| Denominator is 0 | `UNDEFINED` | `NO_BASE` |
| Denominator is 1 to 29 | `UNDEFINED` | `LOW_BASE` |
| Denominator is 30 or more | the rounded percentage | `OK` |

The two causes are not interchangeable. A denominator of zero is a rate that does not exist, because there is nothing to divide; it is reported as `NO_BASE` whether the segment has no rows in the extract at all or has rows of which none were eligible. A denominator between 1 and 29 is a rate that exists but is too thin to publish; it is reported as `LOW_BASE`. Using one code for both loses the distinction the policy exists to make.

The `Rate` cell of an undefined row holds the literal text `UNDEFINED`. It does not hold `0`, `0.00`, an empty cell, `null`, `N/A`, `#DIV/0!`, or the rate the thin sample would have produced. An undefined rate rendered as a zero reads as a real and terrible result, which is the specific misreading this policy was written to prevent — and a thin sample rendered as its own rate is the error the threshold exists to prevent, whatever the arithmetic happens to produce.

## 8. Total row

The output carries one final row with `Segment` = `TOTAL`.

- `Numerator` — the sum of the numerators of the **published** segments only.
- `Denominator` — the sum of the denominators of the **published** segments only.
- `Rate` — the pooled rate, `Numerator / Denominator * 100`, rounded by section 6. It is not the mean of the per-segment rates.
- `ReasonCode` — `OK`, unless the pooled denominator itself falls under section 7, in which case section 7 applies to the total as well.

A segment whose rate is suppressed contributes nothing to the total row — not its numerator, not its denominator. Its counts are still shown on its own row; they are simply not aggregated.

## 9. Output shape

Write `conversion_by_segment.xlsx` to the workspace root, with a sheet named `Conversion`. `Format_Example.xlsx`, alongside this document, shows the shape with placeholder segments.

Row 1 is the header. The columns, in this order:

| Column | Contents |
|---|---|
| `Segment` | the `segment_id` exactly as spelled in `segments.csv`; `TOTAL` on the final row |
| `Numerator` | whole number |
| `Denominator` | whole number |
| `Rate` | a number rounded per section 6, or the text `UNDEFINED` |
| `ReasonCode` | `OK`, `LOW_BASE` or `NO_BASE` |

One row per segment in `segments.csv`, in ascending `segment_id` order, then the `TOTAL` row last.

**Record values, not formulas.** Every cell holds the computed result. A workbook written outside Excel carries no cached value behind a formula, so a formula cell reaches downstream readers as a blank.

## 10. Workings file

Write `workings.json` to the workspace root alongside the workbook, with exactly this shape:

```json
{
  "metric": "conversion_rate_by_segment",
  "period_start": "2026-02-01",
  "period_end": "2026-02-28",
  "rows_read": 0,
  "eligible_visits": 0,
  "excluded": {
    "duplicate_visit_id": 0,
    "unknown_segment": 0,
    "outside_period": 0,
    "internal_channel": 0,
    "void_status": 0
  },
  "segments_published": 0,
  "segments_suppressed": {
    "LOW_BASE": 0,
    "NO_BASE": 0
  },
  "total_numerator": 0,
  "total_denominator": 0,
  "total_rate": 0.0
}
```

- `rows_read` — data rows in `events.csv`, header excluded.
- `eligible_visits` — rows passing section 3.
- `excluded` — the five counts of section 4, which must balance against `rows_read`.
- `segments_published` — segments whose `ReasonCode` is `OK`, the `TOTAL` row excluded.
- `segments_suppressed` — the count of segments under each undefined reason code, the `TOTAL` row excluded.
- `total_numerator`, `total_denominator`, `total_rate` — the `TOTAL` row of the workbook, with `total_rate` as a number.

The zeros above are placeholders for the shape; replace every one of them with the figure it names.
