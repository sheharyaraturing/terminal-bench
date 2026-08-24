# context-mesh/order-fanout

Revenue per customer from orders joined to order lines, where the order total is authoritative.

Scenario F2 · Join fan-out, from `SCENARIOS-finance-dataops.md`.

The agent is handed four CSV extracts and one metric definition, and asked for revenue by customer plus the standard Domain-2 workings record. The arithmetic is addition. The difficulty is that the natural analytic shape — join `orders` to `order_lines`, then aggregate `orders.order_total` — is wrong twice over: it multiplies each order's total by the number of lines the order carries, and, being an inner join, it silently drops the one in-scope order that has no lines at all. `metrics/Definitions.md` says the order total is authoritative and that line amounts allocate rather than reconcile, so the correct measure is taken at order grain and the line table is only ever counted, never summed.

The workings record is what makes the bug visible instead of merely fatal: it asks for the in-scope row count before the join and the row count the join produces (24 and 59). A run that reports the same number twice has aggregated at line grain and said so.

The restraint case is a customer holding in-scope orders in two currencies. The definition says currencies are never converted and never added, so that customer's revenue is `UNDEFINED` with reason `mixed_currency` — not a sum, not the majority currency, not a dropped row.

- **Tools** — MCP servers `filesystem,terminal,excel,word,memory`, local tools `claim_done`, all behind the one SSE gateway on `127.0.0.1:8765`. `word` and `memory` are declared and unused (lever L4b); nothing in the workspace is a `.docx` and there is no state to carry between turns.
- **Verifier** — three dimensions under `tests/`, all fractional, no partial credit for doing nothing. `artifacts/` asks whether both files exist, carry the fixed shape **and hold data**: a workbook with the six headers and no rows, and a `workings.json` whose `population` block is still §8's zeros, both score 0 — existence is folded into those two criteria rather than paid for on its own. `revenue/` grades customer name, currency, order count, revenue and `Undefined_Reason` per customer against `tests/expected/revenue_by_customer.xlsx`, scoring `hits / (5 × max(expected, got))` so invented rows dilute rather than pad; separately asserts the undefined customer is reported with the sentinel — `0`, `""`, `null` and a missing row all score zero there; and separately compares the two orderings §7 states, positionally and fractionally (`sheet_layout`: sheet name plus the fraction of columns in the stated position; `row_order`: the fraction of rows in the position `Customer_ID` ascending puts them in). `workings/` grades the headline figure, the six population counts and the definedness block, rejecting a stringified `value`, a missing `denominator` key and an unfilled §8 template.
- **Everything else** — environment, gateway and eval chain are the suite template's, unmodified. See `docs/task-structure/`.

```bash
python3 tasks/new_task.py lint tasks/generated/order-fanout
python3 tasks/new_task.py gate tasks/generated/order-fanout
```

## Difficulty budget

| Lever | Instance |
|---|---|
| L1 overlong observation | **Not instantiated under the suite's default agent.** `data/order_lines.csv` is 94 rows, measured at 11,503 chars rendered — an eighth of the Toolathlon agent's 100,000-char ceiling (`MAX_SINGLE_TURN_RETURN_CHARS`, the loop's own log line); Harbor's built-in agents truncate near 8–10 KB, but they never reach the MCP gateway and this suite is not measured under them, so it arrives whole in one call. `rows_after_join` still cannot be produced without covering all of it, which is an L2 observation floor rather than an L1 ceiling. One vector only. §2 of the definition names the navigation path — `wc -l`, `grep`, `awk`, `sed -n`, or ranged reads through the terminal server — and tells the agent to reconcile its row count against `wc -l`. |
| L2 observation floor | Stated counts: 38 order rows, of which `included` plus the three exclusion counts must equal 38; 94 line rows. Premature-stop lure: `revenue_by_customer.xlsx` is computable from `orders.csv` and `customers.csv` alone, so a run can look finished having never opened `order_lines.csv` — and lose the whole `workings` dimension, a third of the reward, on `rows_after_join`. |
| L3 prior contradiction | Prior: *revenue per customer is `SELECT customer_id, SUM(o.order_total) FROM orders o JOIN order_lines l USING (order_id) GROUP BY 1`.* Environment: §4 says the order total is authoritative, `line_amount` is an allocation that does not reconcile, and each in-scope order contributes its total **exactly once** whatever its line count — so the join may be counted but never aggregated over. Second prior: *an inner join is the default join.* Environment: an in-scope order with no lines is still an in-scope order. |
| L4a parameter/resource strictness | Nothing here survives a constructed guess. `rows_after_join` = 59 requires counting line rows against the 24 in-scope order ids. The sentinel spelling (`UNDEFINED`), the reason code (`mixed_currency`), the three exclusion keys and their precedence order exist only in §3 and §5. Rounding is half-up and three customers sit exactly on a half-cent tie (2418.625, 905.625, 2230.125), where Python's default `round()` gives the wrong cent for all three. |
| L4b tool-name confusability | `word` and `memory` declared and unneeded, alongside `filesystem`, `terminal` and `excel`. |
| L5 state distractors | 105 irrelevant records to 94 relevant, ≈1.12 : 1. 14 of 38 order rows are out of scope; 35 of 94 line rows belong to out-of-scope orders; all 53 rows of `shipments.csv` are irrelevant and `shipments` fans out too, so joining it repeats the bug in a second place; 3 of 14 customers never appear on the sheet. `shipments.csv` is left for the agent to exclude on the evidence — §2 gives its grain and its columns (carrier, parcels, weight) and §4 says revenue comes from `orders.order_total` and nowhere else — rather than being labelled irrelevant in the spec. |
| L6 restraint | CUS-107 holds three in-scope orders, two USD and one EUR. §5 says report `UNDEFINED` with `mixed_currency` rather than resolve it. Graded by its own criterion so guessing a number is visibly distinct from flagging. |
| Traps | 6, tabled below. |
| N1 population from a written definition | The row set is never handed over. §3 defines three exclusion tests, fixes their precedence so the reasons partition the excluded rows, and requires the accounting to balance to 38. Two orders are excluded by a test that is not the first one they match. |
| N2 NULL vs 0 vs absent | Four distinct states in the data: an order with **no** line rows (ORD-2409); a line whose `line_amount` is **NULL** (OL-00045); two lines whose amount is **0.00** (ORD-2436); and an order whose `order_total` is **0.000** (ORD-2436), which §4 says is a real order with a real customer row and a revenue of 0.00, not an absence. |
| N3 as-of correctness | Not carried. The catalog's coverage matrix marks F2 `—` for N3, and the period is pinned to fixed literal dates in §1 rather than resolved against a clock. |

## Traps

| Trap | Where | The lazy algorithm it separates |
|---|---|---|
| An order with four lines | ORD-2422, CUS-109, total 1880.000 | Join-then-aggregate. Fan-out multiplies the order total by the line count; CUS-109 reads 8586.50 instead of 2235.50. Twelve other in-scope orders carry three or four lines, so the error is spread across most of the sheet rather than isolated to one row. |
| An in-scope order with no lines | ORD-2409, CUS-110, total 990.000 | `INNER JOIN` where the order must be kept. The order vanishes, CUS-110 loses 990.00 and its order count drops from 2 to 1 — the opposite-signed error to fan-out, so the two do not cancel and cannot be corrected by a single scale factor. |
| A customer with orders in two currencies | CUS-107: USD 1200.000, EUR 640.000, USD 310.000 | `SUM(order_total) GROUP BY customer_id` with no currency partition. Produces 2150.00 where the definition wants `UNDEFINED`. Also separates "drop the awkward customer", which loses the row entirely. |
| A line with a NULL amount | OL-00045 on ORD-2418 | Reconstructing revenue by summing `line_amount`. Line allocations run at 86–114% of the order total by design and one is missing outright, so a line-sum lands plausibly near the right figure and is never right. |
| Half-cent ties on three customers | CUS-101 2418.625, CUS-102 905.625, CUS-110 2230.125 | `round()` and `f"{x:.2f}"`, which round half to even and give 2418.62, 905.62 and 2230.12. §6 names half-up. Also separates rounding each order before summing. |
| Orders dated exactly on both period bounds | ORD-2406 (2024-07-01), ORD-2436 (2024-09-30), against ORD-2405 (2024-06-30) and ORD-2437 (2024-10-01) | Exclusive bounds. Dropping either boundary order moves both the headline figure and two exclusion counts; ORD-2436 is also the zero-total order, so dropping it removes CUS-111's only row. |

## Notes

The derivations are independent as the checklist requires. The fixtures carry the answer by construction. `solution/solve.sh` re-derives it by parsing `metrics/Definitions.md` — period bounds, exclusion precedence, sentinel, reason code, reporting currency, sheet name and both output filenames all come out of the document, and the column order comes out of `metrics/Format_Example.xlsx` — and never reads the answer key. `tests/*/check.py` compares the artifact to `tests/expected/`.

The naive method is join-then-sum. It applies the population filters competently and still scores 0.667, losing the headline figure, four of six population counts, the undefined row and nine of eleven revenue figures. It writes the sheet in the stated layout and row order, so the two ordering criteria pay it in full — they measure layout, not method.

Graders load the workbook twice — `data_only=True` for cached values, then again with formulas intact to fill in what the first read returned as `None` — and scan every sheet for the required header rather than trusting `.active`. A cell that still holds a formula is named in the failure line by sheet and coordinate, with the §7 rule it breaks, so a run debugged from `reward-details.json` is not sent after a phantom blank; the line is emitted once per sheet, so a wholly formula-written answer does not flood the log.

**Waiver — formula tolerance.** The checklist asks that a formula-written correct answer still score 1.0. It does not here: a workbook whose `Orders` and `Revenue` cells hold formulas rather than literals scores 0.924 overall (`revenue` 0.771). The graders load the workbook twice and name the offending cell as `Revenue!D2 holds the formula '=3' … §7 of metrics/Definitions.md requires recorded values, not formulas`, which is the checklist's "report clearly" branch, and §7 states the values-not-formulas rule in bold before the agent writes anything. `openpyxl` cannot evaluate a formula and the verifier image carries no expression engine, so the rule is stated, enforced and diagnosed rather than evaluated.

**Ordering is graded, not stated.** Every ordering and layout sentence in the spec is now measured: the sheet name `Revenue` and the six-column order by `revenue.sheet_layout`, the `Customer_ID` ascending row order by `revenue.row_order`, both fractional. Measured: a correct sheet in descending row order scores 0.970 overall (`row_order` 0.091), and a correct sheet with two columns swapped on a sheet named `Sheet1` scores 0.972 (`sheet_layout` 0.167). Both scored 1.000 before. §3's exclusion *precedence* is graded through the three exclusion counts, which move if the tests are applied in another order.

**No free points for a stub.** A headers-only `revenue_by_customer.xlsx` (sheet `Revenue`, the six headers, no rows) together with §8's template copied back with its zeros in it scores **0.000** overall — `artifacts` 0.000, `revenue` 0.000, `workings` 0.000. The `file_exists` criteria that used to pay 0.5 of the `artifacts` dimension for two empty files are gone; existence now only counts inside a criterion that also requires content.

`new_task.py gate` (the Docker build) has not been run for this task; `lint` and the `check-ignore` sweep have.
