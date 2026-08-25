PR #30 improves the task, but while fixing the old rounding problem, it introduces **two new rules that the data does not test**.

## Overall status

> **Accept with fixes — no blocker, but not delivery-ready until real model runs exist.**

The answer key and grader are correct:

* Oracle: `1.0`
* Key comparison: `0` mismatches
* Empty output: `0.0`
* One junk row: `0.20`
* Grader: PASS
* Real model evidence: not assessed

## What PR #30 fixed

The previous issue said rounding each order separately produced the same answer as summing first and rounding once.

PR #30 changed:

```text
ORD-2408: 1420.500 → 1420.505
```

Now:

* Correct sum-then-round method gives `2418.63`.
* Incorrect round-each-order method gives `2418.64`.

So that old issue is properly fixed.

However, the PR added new rules and data, and two of those rules are now inert.

---

## Issue 1 — The two undefined-reason conditions never overlap

### New rule

§5 apparently has two reasons for an undefined customer result:

1. `mixed_currency`
2. `missing_order_total`

It says to test them in order and use the **first applicable reason**, so one customer never receives two reasons.

### Current data

* `CUS-107` has EUR and USD orders, so it triggers `mixed_currency`.
* `CUS-108` has one blank order total, so it triggers `missing_order_total`.

But no customer triggers both.

Therefore, it does not matter which rule is checked first:

```text
mixed_currency → missing_order_total
```

or:

```text
missing_order_total → mixed_currency
```

The answer remains identical and still scores `1.0`.

### Concrete example

Current:

| Customer | Mixed currencies? | Missing total? | Result                |
| -------- | ----------------: | -------------: | --------------------- |
| CUS-107  |               Yes |             No | `mixed_currency`      |
| CUS-108  |                No |            Yes | `missing_order_total` |

To test precedence, create one customer with both conditions. For example, make one of CUS-107’s in-scope order totals blank:

| Customer | Mixed currencies? | Missing total? |
| -------- | ----------------: | -------------: |
| CUS-107  |               Yes |            Yes |

Then:

* If `mixed_currency` is checked first → reason is `mixed_currency`.
* If `missing_order_total` is checked first → reason is `missing_order_total`.

Now rule order changes the answer and becomes testable.

### Why it matters

The methodology emphasizes “report the first applicable reason,” but an agent can ignore that instruction and still receive full credit.

---

## Issue 2 — `unknown_customer` being first in the exclusion cascade is not tested

### New rule

§3 says `unknown_customer` must be checked before other exclusions, such as:

* internal account,
* out of period,
* cancelled or draft.

### Current data

The only unknown-customer order is:

```text
ORD-2419 → CUS-113
```

But that order is:

* inside the reporting period,
* delivered,
* not otherwise excluded.

Therefore, it is classified as `unknown_customer` regardless of whether that check is first or last.

### Example

Current unknown order:

| Unknown customer? | Out of period? | Cancelled? |
| ----------------: | -------------: | ---------: |
|               Yes |             No |         No |

There is no conflict, so precedence is irrelevant.

To test it, add an unknown-customer order that is also cancelled:

| Unknown customer? | Cancelled? |
| ----------------: | ---------: |
|               Yes |        Yes |

Then:

* Unknown checked first → increment `unknown_customer`.
* Cancelled checked first → increment `cancelled_or_draft`.

The order remains excluded either way, but `workings.json` should record it in a different exclusion bucket.

### Why it matters

The `unknown_customer` bucket itself is tested and important. Only the claim that it must be checked **first** is currently untested.

---

## Issue 3 — Exact uppercase and exact text are not enforced

The definition says:

```text
UNDEFINED — upper case, exactly that spelling
```

But the grader converts text to lowercase before comparing it.

Therefore, all these receive full credit:

```text
UNDEFINED
undefined
Undefined
uNdEfInEd
```

The same normalization affects other string fields. For example:

```text
Northwind Trading Co
```

and:

```text
northwind trading co
```

may be treated as identical even though §7 says names must be copied exactly.

### Fix

The report recommends relaxing the wording:

> Matching is case-insensitive; surrounding whitespace is ignored.

This matches the existing grader and is more user-friendly.

Alternatively, enforce exact case in the grader—but that would be stricter and could break the current oracle unless updated carefully.

---

```