# context-mesh/policy-vintage

Decide expense claim lines under the policy version in force on the expense date

Thirty-seven travel subsistence lines across twelve claims have to be approved, rejected or held. Each line is judged under the version of the group expense policy that was in force on the day the expenditure was incurred, which is almost never the version in force when the claim was submitted and is not the newest version on disk. Four policy documents sit in the tree — an archived v2, an approved v3, an approved v4 whose effective date falls inside the claim window, and a v5 that has been drafted but never approved — and the agent has to read a status and an effective date off each one before it can decide anything. Having chosen a version it then has to pull three figures out of that version and not out of its neighbour: the receipt threshold from section 4, the daily subsistence ceiling from Appendix B, and the settlement rate from Appendix C. The two approved versions disagree on every non-sterling settlement rate, on every ceiling they both name, and on the receipt threshold, and the older version's ceiling is the *higher* one for two destinations — so an agent that decides the version wrongly does not merely mislabel a column, it changes verdicts in both directions. The prompt itself is [instruction.md](instruction.md); every rule lives in `policy/AP_Expense_Manual.docx` in the workspace.

- **Tools** — MCP servers `filesystem,terminal,excel,word,memory`, local tools `claim_done`, all behind the one SSE gateway on `127.0.0.1:8765`. `memory` is declared and never needed.
- **Verifier** — three Reward Kit dimensions, all fractional. `tests/artifacts` checks that `decisions.xlsx` exists, carries at least one decided line, sits on a worksheet named `Decisions`, and carries the five required columns in the order manual 6.4 states — the order criterion scores the fraction of columns standing in the right position, and every artifacts criterion is gated on the sheet holding data, so a headers-only shell scores 0.000 overall rather than banking a third of the reward; `tests/versioning` scores the fraction of lines attributed to the governing policy version; `tests/disposition` scores `Verdict` and `Reason` together, half a point each. Every column the instruction demands is graded. Both content dimensions scan all worksheets rather than trusting `.active`, read the workbook twice so a formula-written answer still grades, and divide by `max(len(expected), len(got))` so padding the sheet lowers the score. On the held line, `0`, `""`, `null` and a missing row all score zero — only the `UNDETERMINED` / `HOLD` / `NO_EXPENSE_DATE` triple counts. A formula cell with no cached result is reported as `Decisions!C2 holds the formula '=…' and no cached value`, once per sheet, so a failed run names its cause instead of pointing at a phantom blank.
- **Everything else** — environment, gateway and eval chain are the suite template's, unmodified. See `docs/task-structure/`.

## Difficulty budget

| Lever | Instance |
|---|---|
| L1 overlong observation | **Not instantiated under the suite's default agent.** One vector: each `Expense_Policy_v*.docx` measures at most 13,001 chars of extracted text — an eighth of the Toolathlon agent's 100,000-char ceiling (`MAX_SINGLE_TURN_RETURN_CHARS`, the loop's own log line); Harbor's built-in agents truncate near 8–10 KB, but they never reach the MCP gateway and this suite is not measured under them — so a policy arrives whole and the two deciding tables at the end are never cut off. Navigation is stated in manual §6.5 — `get_document_outline`, `find_text_in_document` and `get_paragraph_text_from_document` on the `word` server, or `python3` with `docx` from `terminal`. |
| L2 observation floor | 33 independent document facts before the first line can be decided: 4 policy cover blocks (version, status, effective date), 2 receipt thresholds, 2 Appendix B tables of 7 rows, 2 Appendix C tables of 4 rows, and 5 procedural rules in the manual — plus the 37 line records themselves. |
| L2 premature-stop lure | The first three claims in the register (`CLM-2041`, `CLM-2043`, `CLM-2044`, eight lines) are entirely post-change, so "v4 everywhere" reproduces the opening block of the answer exactly and looks confirmed before the boundary is ever met. |
| L3 prior contradiction | Prior: *the newest policy applies.* Environment: 22 of the 36 dated lines are governed by the **older** v3, because the v4 effective date sits three-quarters of the way through the claim window. Second prior: *apply whichever version lets the line through.* Environment: v3's ceiling is higher for Dublin (71.00 vs 64.00) and Zurich (88.00 vs 84.00) while v4's is higher for Amsterdam, Berlin and Lisbon, so that heuristic is wrong in both directions. |
| L4a parameter/resource strictness | Neither the settlement rate nor the ceiling can be constructed — both must be read out of the governing version's own appendix, and the two approved versions share no non-sterling value. `Porto` is named in v3's Appendix B but not v4's, `Oslo` in v4's but not v3's, `Madrid` in neither: a guess of "not listed, so skip it" misses the `All other locations` row that actually decides those three lines. Claim IDs are non-sequential (`CLM-2044` is followed by `CLM-2047`), so a constructed ID lands on nothing. |
| L4b tool-name confusability | `memory` is declared in `MCP_SERVERS` and is never needed. The filename space is crowded to match: four documents named `Expense_Policy_v*.docx` across two directories, and two claim registers with the same nine column headers. |
| L5 state distractors | 14 already-settled lines in `archive/claims_settled_2026Q1.xlsx` against 37 live lines (0.38 : 1); 2 non-governing policy documents against 2 governing ones (1 : 1); inside each governing policy, 7 accommodation ceilings in Appendix A against 7 subsistence ceilings in Appendix B (1 : 1) and ten body sections that carry no figure the task needs. Every distractor is separated from signal by evidence in the workspace: a `Status:` line, a settlement date outside the window the manual pins, or an appendix heading. |
| L6 restraint | `CLM-2055` line 1 has no expense date. The manual says hold it — `UNDETERMINED` / `HOLD` / `NO_EXPENSE_DATE` — and says in terms not to infer the date from the submission date. The two lines either side of it are the same traveller, the same destination and nearly the same amount, and they resolve to different versions and opposite verdicts, so there is no safe neighbour to copy. |

## Traps

| Trap | Lazy algorithm it separates |
|---|---|
| `CLM-2047`, `CLM-2051`, `CLM-2052`, `CLM-2063` — submitted after 2026-05-18, incurred before it | keying the version off the submission date |
| `CLM-2048` — four lines straddling 2026-05-18, two under v3 and two under v4 | choosing one version per claim rather than per line |
| `CLM-2048` line 2, dated exactly 2026-05-18 | treating the effective date as exclusive rather than inclusive |
| `policy/Expense_Policy_v5.docx`, `Status: DRAFT`, effective 2026-11-01 | taking the highest-numbered or most recently written policy on disk |
| `archive/Expense_Policy_v2.docx`, `Status: ARCHIVED` | treating every policy document in the tree as a live candidate |
| v3 Dublin 71.00 against v4 Dublin 64.00, v3 Zurich 88.00 against v4 Zurich 84.00 | applying whichever version's ceiling lets the line through |
| `CLM-2051` line 1 — EUR 64.45 × 0.9000 = 58.005 against a 58.00 ceiling | rounding half-to-even, or rounding the binary float that reads 58.00499999 |
| `CLM-2051` line 2 exactly on the ceiling (62.00) and line 3 exactly on the receipt threshold (25.00), with line 4 a penny below it | reading the ceiling or the threshold as exclusive |
| `CLM-2060` line 1 — GBP 18.00 with no receipt, which passes v3's 25.00 threshold and fails v4's 15.00 | carrying one version's receipt threshold across the boundary |
| `CLM-2052` line 1 (Oslo, unnamed in v3) and `CLM-2059` line 3 (Madrid, unnamed in either) | dropping or blanking a line whose destination is missing from the appendix instead of using `All other locations` |
| Appendix A, a destination × ceiling table of the same shape sitting *before* Appendix B in every version, with nothing anywhere saying it does not apply — section 5 routes subsistence to Appendix B, section 6 routes the room charge to Appendix A, and manual 6.3(d) names Appendix B | grabbing the first destination table the document yields |

## Gates

The naive method is the lazy algorithm: it reads the same documents, applies the same receipt, conversion and ceiling tests, and differs only in choosing one approved version per claim by the submission date and dating the held line from the submission. It produces a well-formed register and scores 0.748 — 0.541 on versioning, 0.703 on disposition.

A headers-only `decisions.xlsx` — the five column names and no rows — scores 0.000 overall: 0.000 on each of the three dimensions.

```bash
python3 tasks/new_task.py lint tasks/generated/policy-vintage
python3 tasks/new_task.py gate tasks/generated/policy-vintage
```

