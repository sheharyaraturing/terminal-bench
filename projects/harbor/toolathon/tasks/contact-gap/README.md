# context-mesh/contact-gap

Identify customers with no support contact in the reporting period from a two-table extract.

The agent is handed two CSVs and a metric specification and asked which customers never reached support during the period. The arithmetic is a set difference; the work is deciding what is in each set. Deriving it means collapsing a customers export that repeats ids, classifying every ticket through a stated four-step order in which the first matching test wins, and noticing that the extract's contact evidence is punctured in four independent ways — a ticket with no `customer_id` at all, tickets naming customers that do not exist, tickets that were soft-deleted, and tickets sitting just outside the period on both sides. The inference the task forces is that the anti-join every model reaches for first — `WHERE customer_id NOT IN (SELECT customer_id FROM tickets)` — collapses to the empty set the moment one ticket carries a NULL key, and returns that empty set without erroring. Nothing in the environment announces this; the only signal is that the answer looks implausible against a 96-customer population, and the specification's requirement that `customers_with_contact + value == customers_total` is the check that surfaces it.

- **Tools** — MCP servers `filesystem,terminal,excel,word,memory`, local tools `claim_done`, all behind the one SSE gateway on `127.0.0.1:8765`. `word` and `memory` are declared and unused (lever L4b): nothing in the workspace is a `.docx` and nothing needs to be remembered across turns.
- **Verifier** — four dimensions under `tests/`, every one a fraction. `artifacts` grades the shape section 8 and section 9 state and nothing else: the sheet is named `NoContact`, the four columns sit in the stated order on the first row, the sheet carries at least one data row, the rows are sorted ascending by `customer_id` (scored as the fraction of rows sitting where the sort would put them), and the ten workings keys are present and filled in rather than left at the section 9 placeholder. Existence alone pays nothing, so a headers-only shell scores 0.000 overall. `cohort` grades the customer set, with repeated and invented rows charged to the denominator; `attributes` grades `customer_name`, `segment` and `data_issue` per row, plus a criterion isolating the undefined cells that rejects `0`, `""`, `null` and a dropped row; `workings` grades the ten figures in `workings.json`, the excluded-row counts weighted equally with the headline. `cohort` and `attributes` scan every sheet for the header rather than trusting `.active` — the sheet name is graded once, in `artifacts`, rather than three times — and every workbook is loaded twice so a formula-written answer surfaces as its formula text, named once per sheet as `NoContact!A2 holds the formula ... and no cached value`, instead of as a phantom blank.
- **Everything else** — environment, gateway and eval chain are the suite template's, unmodified. See `docs/task-structure/`.

## Layout

| Path | Holds |
|---|---|
| `environment/task/initial_workspace/metrics/Definitions.md` | the specification. Authored, not generated — it is the fixture that carries every rule. |
| `environment/task/initial_workspace/metrics/Prior_Period_Note.md` | authored distractor: the closed Q1 run of the same metric. |

```bash
python3 tasks/new_task.py gate tasks/generated/contact-gap
```

## The answer

96 distinct customers across 98 rows; 75 reached support inside 2025-04-01 … 2025-06-30 and 21 did not. 405 tickets classify as 361 contact, 4 orphan, 11 soft-deleted and 29 out of period. `contact_rate` is 75/96 = 0.78125 exactly, which is 0.7813 half-up and 0.7812 under the banker's rounding a default `round()` applies.

## Difficulty budget

| Lever | Requirement | Instance in this task |
|---|---|---|
| L1 overlong observation | ≥1 vector, ≤2, navigable | **Not instantiated under the suite's default agent.** One vector: `data/tickets.csv`, 405 rows, measured at 24,674 chars rendered — a quarter of the Toolathlon agent's 100,000-char ceiling (`MAX_SINGLE_TURN_RETURN_CHARS`, the loop's own log line); Harbor's built-in agents truncate near 8–10 KB, but they never reach the MCP gateway and this suite is not measured under them, so it arrives whole in one call. The navigation path below is available and unnecessary; growing the file past 100,000 chars is what would instantiate the lever. Section 2 of `Definitions.md` states the navigation path — `wc -l`, `grep`, `awk`, `sed -n` through the terminal server, or reading the file from a script — and the image ships ripgrep and python. |
| L2 observation floor | a stated count, plus one named premature-stop lure | Section 2 states the floor: 98 customer data rows and 405 ticket data rows, and says a mismatch means the read was partial. The lure is `metrics/Prior_Period_Note.md`, which hands over a complete, plausible, wrong set of workings (`value` 18, `contact_rate` 0.8022, orphan 2, soft-deleted 6) for the *previous* quarter. Nothing in it says it does not apply; what distinguishes it is evidence — it is titled as the closed Q1 2025 run, it states its own period as 2025-01-01 to 2025-03-31 against section 1's 2025-04-01 to 2025-06-30, and it names its source as the archived `2025-01-06` export with 91 and 214 data rows against section 2's 98 and 405. The exclusion is inferable three ways over and handed over none. |
| L3 prior contradiction | ≥1, as *prior → what the environment says* | Three. **Prior:** an anti-join with `NOT IN` (or `~df.customer_id.isin(...)`) answers the question → **environment:** one ticket carries an empty `customer_id`, so SQL's three-valued logic makes the predicate UNKNOWN for every candidate and the result set is empty, silently. **Prior:** `COUNT(*)` over the customers export is the population → **environment:** the export repeats two ids, and section 3 counts distinct ids. **Prior:** `round(x, 4)` implements four-decimal rounding → **environment:** section 6 names half-up, and 75/96 is exactly 0.78125, a tie, so the default banker's rounding differs in the fourth place. |
| L4a parameter/resource strictness | ≥1 lookup that defeats a constructed guess | Three unguessable literals, none of them in the prompt: the sentinel `UNDETERMINED`, the reason codes `AMBIGUOUS_NAME` / `MISSING_SEGMENT` / `NONE`, and the metric string `customers_without_contact`. The sheet name `NoContact` is output contract and is stated in the prompt, so it is not one of them. Column spelling and order are carried by `metrics/Format_Example.xlsx`, which the specification names as the authority. |
| L4b tool-name confusability | ≥1 unrelated MCP server declared | Two: `word` (no `.docx` anywhere in the workspace) and `memory` (single-pass task, nothing to persist). Five servers are declared, three are needed. |
| L5 state distractors | the ratio of irrelevant to relevant records, stated | Customers: 75 irrelevant to 21 relevant, **3.6 : 1**. Tickets: 361 of 405 rows are ordinary contact that changes nothing, against 44 that are excluded and 8 that single-handedly decide a customer's disposition — **8.2 : 1** by row. Plus one whole distractor document, `Prior_Period_Note.md`. |
| L6 restraint | ≥1 flag-don't-guess case | `C-1043` appears on two rows of `customers.csv` — same segment, same region, same signup date, two different names (`Stanwick Analytics`, `Halden Freight Group`). It has no contact, so it must be reported, and section 7 says report it with `customer_name` = `UNDETERMINED` and `data_issue` = `AMBIGUOUS_NAME` rather than picking either name. The temptation is real: the first row wins under any naive `dict(rows)` build, and both names are perfectly plausible. The control is `C-1017`, repeated verbatim, which must collapse silently with `data_issue` = `NONE` — so the rule being tested is *conflict*, not *repetition*. |
| Traps | ≥4, each naming the lazy algorithm it separates | Seven, below. |
| N1 population from a written definition | population derived, not handed over | The row set exists nowhere in the workspace. It is the difference between distinct `customer_id` in `customers.csv` and the customers named by class-4 tickets, and both sides need assembling. |
| N2 NULL vs 0 vs absent | three different things | An empty `customer_id` is an orphan, not a customer and not a zero (section 4). An empty `segment` is `UNDETERMINED` + `MISSING_SEGMENT`, not blank and not `0` (section 7). A customer absent from `tickets.csv` entirely is a perfectly ordinary member of the answer. The grader rejects `0`, `""`, `null` and a missing row where the answer is undefined. |
| N3 as-of correctness | point-in-time | Incidental, by design — this family has no slowly-changing dimension. What it does carry is the period pin: the reporting period is written into `Definitions.md` as a literal date range, the extract is declared a frozen snapshot, and the specification says in terms that the period is not derived from today's date. Nothing in the task moves with the calendar. |

## Traps

| # | Trap | Lazy algorithm it separates | Cost when it bites |
|---|---|---|---|
| 1 | `T-200229` carries an empty `customer_id`, inside the period, not deleted | `customer_id NOT IN (SELECT customer_id FROM tickets)`, and pandas' `~customers.customer_id.isin(tickets.customer_id)` variant that keeps NaN in the right-hand side. Under SQL semantics the predicate is UNKNOWN for every row and the answer is the empty set — no error, no warning | catastrophic: `cohort` and `attributes` both 0 |
| 2 | Three tickets name `C-9001`, `C-9007` and `C-9013`, none of which is in `customers.csv` | computing `customers_with_contact` as `COUNT(DISTINCT customer_id)` over in-period tickets, which counts identifiers that are not customers | `customers_with_contact`, `value` and `contact_rate` |
| 3 | `C-9013`'s orphan ticket is *also* soft-deleted, and one out-of-period ticket is soft-deleted while another names an unknown customer | classifying with independent `WHERE` clauses instead of the stated first-match order, which double-counts a ticket into two classes | `orphan_tickets` and `soft_deleted_tickets` |
| 4 | `C-1034` and `C-1055` have exactly one in-period ticket each and it is soft-deleted; `C-1078` has two and both are | ignoring `deleted_at`, or treating a soft-deleted ticket as evidence of contact | three customers lost from the cohort |
| 5 | `C-1023`'s only ticket is 2025-03-31 and `C-1029`'s only ticket is 2025-07-01 — one day outside on each side | joining without a period filter, or filtering on the wrong column | two customers lost from the cohort |
| 6 | `C-1003`'s only in-period ticket is on 2025-04-01 and `C-1007`'s is on 2025-06-30, both endpoints | exclusive bounds — `> start AND < end` — which wrongly adds both customers to the answer | two invented rows, charged to the denominator |
| 7 | `C-1017` and `C-1043` each appear on two rows of `customers.csv` | `len(rows)` as the population, and a `dict(rows)` build that silently keeps whichever name came last | `customers_total`, `customers_with_contact`, `contact_rate`, plus a duplicated output row |

## Gate results

| Strategy | Reward | artifacts | attributes | cohort | workings |
|---|---|---|---|---|---|
| oracle | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| nop | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| naive | 0.175 | 0.300 | 0.000 | 0.000 | 0.400 |
| stub | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

The stub row is the empty scaffold: `no_contact.xlsx` carrying the `NoContact` sheet and its header row and nothing else, `workings.json` carrying the ten keys with no values. It is graded because a shell that banks a quarter of the reward for producing no answer is the failure mode `nop` cannot see. Copying section 9's placeholder block verbatim instead of nulling it scores 0.100 rather than 0.000 — `metric`, `period_start` and `period_end` are literal strings the specification states, so a submission carrying them has three of the ten workings right and is credited for exactly that.

The naive method implements the anti-join with SQL's three-valued logic spelled out, so trap 1 fires exactly as it would against a real database: the cohort comes back empty while the workbook stays well-formed. The empty cohort costs it the `artifacts` dimension too — a sheet with no data rows is a shell — which is why `artifacts` reads 0.300 and not 1.000. Traps 2, 3 and 7 fire alongside it in `workings`, which is why the naive keeps only `metric`, `period_start`, `period_end` and `out_of_period_tickets`.

**Lucky-number check.** The naive's figures are 0 customers, `customers_total` 98, `contact_rate` 1.0, `orphan_tickets` 3 and `soft_deleted_tickets` 12, against a truth of 21, 96, 0.7813, 4 and 11. No plausible wrong method reaches the correct set: dropping the soft-delete rule gives 18, dropping the period filter gives 19, exclusive bounds give 23, and row-counting the export gives a population of 98. The `contact_rate` tie is the tightest — half-up 0.7813 against banker's 0.7812 — and it is graded to 1e-9, so the two do not collide.
