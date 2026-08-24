# context-mesh/restatement-vintages

Rebuild the restatement comparison from a bitemporal financials filing table.

Scenario **F3 · Restatement vintages** from the Finance & Data Ops catalog. `financials.csv` is a filing register keyed by `reported_for_period` *and* `as_of_date`: one row per filing of one figure, several vintages per period, filed in an order that interleaves periods. The pack the agent must build puts two point-in-time answers side by side — the figure in force now (the latest vintage) and the figure the auditors signed (the original vintage) — with the vintage date each came from. The prompt is [instruction.md](instruction.md); every rule lives in `metrics/Reporting_Policy.md` inside the workspace.

The difficulty is not the arithmetic; the only arithmetic is one subtraction and one division. It is that **the newest row for a period is usually not its latest vintage**. The newest row may be management basis, may fall after the reporting cutoff, may be a registered filing with no figure, or may belong to a period the close calendar never closed. Four of the eight covered periods have their newest row disqualified for one of those reasons, and three periods cannot be reported at all and must come back `UNDEFINED` with three different reason codes.

- **Tools** — MCP servers `filesystem,terminal,excel,word,pptx`, local tool `claim_done`, all behind the one SSE gateway on `127.0.0.1:8765`. `pptx` is declared and never needed (lever L4b); `word` opens one superseded memo and nothing else.
- **Verifier** — six Reward Kit dimensions under `tests/`, every one a fraction: `artifacts` (both files present, populated, and carrying the fixed layout), `latest`, `original`, `revision`, `definedness` and `workings`. `latest` and `original` are deliberately separate so a run that computed the easy column and stopped scores differently from a run that computed both and got them wrong. Nothing pays for a stub: a workbook holding only the header row and a `workings.json` holding only the policy's key skeleton score **0.000 overall**, because every criterion in `artifacts` needs at least one data row and the `workings` dimension refuses to hand out its five copied-from-the-policy constants to a file that counts nothing.
- **Everything else** — environment, gateway and eval chain are the suite template's, unmodified. See `docs/task-structure/`.

## Layout

| Path | Holds |
|---|---|
| `environment/task/initial_workspace/` | `financials.csv` (33 filings), `close_calendar.csv` (11 periods), `metrics/Reporting_Policy.md`, `metrics/Format_Example.xlsx`, `metrics/Close_Memo.docx` |
| `tests/expected/` | `vintage_report.xlsx` (8 rows) and `workings.json` (14 graded keys) |
| `solution/solve.sh` | the oracle: parses every parameter out of the published policy, then re-derives from the CSVs |
| naive method | group by period, newest row wins, oldest row is the original, no filters at all |

## Difficulty budget

| Lever | Instance | Where |
|---|---|---|
| L1 overlong observation | **Not instantiated under the suite's default agent.** One vector, `Reporting_Policy.md`, measured at 8,891 bytes — past the ~8–10 KB per-call ceiling of Harbor's built-in agents, but an order of magnitude inside the Toolathlon agent's, whose loop logs `MAX_SINGLE_TURN_RETURN_CHARS: 100000`. Measured, not assumed: in the one recorded trial the file arrived whole in a single observation of 9,083 chars (`runs/all-luna/restatement-vintages__5RjJzne`, traj message 5) and the agent never called `terminal` at all. The navigation path is still stated in the contents block (`grep -n '^## '`) and `terminal` plus ripgrep are in the image, so the lever is available — it simply does not bite at this size. Growing the spec past 100 KB is the only way to instantiate it here. | `metrics/Reporting_Policy.md` |
| L2 observation floor | 8 covered periods × 2 vintage selections = 16 point-in-time lookups, plus 8 definedness verdicts, plus 14 workings keys — 38 independent facts. **Named premature-stop lure:** `Latest_Amount_USD`. It is the column a reader reaches first, it computes without ever sorting ascending, and the original-vintage half is what gets dropped. | graded as `latest` vs `original` |
| L3 prior contradiction | *prior:* the most recent row for a key is its current value → *environment:* the most recent row is disqualified in 4 of 8 periods (basis, cutoff, missing figure, scope). *prior:* a restatement revises a figure down → *environment:* FY24-Q1 is restated up, 8.00M → 8.18M. *prior:* `round(x, 1)` is half-up → *environment:* the policy names half-up and FY24-Q1 lands exactly on 2.25, where Python's half-to-even gives 2.2. *prior:* an empty numeric cell is 0 → *environment:* it is a filing registered with no figure published. | §4, §5, §7 |
| L4a parameter/resource strictness | the cutoff `2025-11-14` is stated once, in §2, and no constructed guess reaches it: it is not a period end, not the newest filing date, not a quarter boundary, not today. The three reason-code spellings, the `NONE` marker and the six bucket names are likewise lookups, not inventions. | §2, §6, §8 |
| L4b tool-name confusability | `pptx` declared and never used; `excel` and `word` both present with overlapping "open a document" surfaces. | `task.toml` |
| L5 state distractors | 24 of 33 register rows are excluded, 9 are included — **2.67 : 1 irrelevant to relevant**. Nine management-basis filings shadow the statutory ones on the same dates, an `under_review` period carries two clean-looking statutory vintages, and `Close_Memo.docx` states an older cutoff, the opposite reporting basis and the opposite rounding mode, stamped SUPERSEDED in its first line so the conflict is resolvable from evidence. | `financials.csv`, `metrics/Close_Memo.docx` |
| L6 restraint | **one case:** FY25-Q1. Its only figures are two preliminary flash estimates, the later one revised, and a management-basis final. The pack must report `UNDEFINED` / `no_reportable_vintage` rather than the 7,655,000 sitting right there. | FY25-Q1 |
| Traps | 12, tabulated below | `financials.csv`, `close_calendar.csv`, policy §2–§8 |
| N1 population assembly | the row set is derived twice from prose: which *periods* the pack covers (close calendar status) and which *filings* are selectable (basis, vintage type, figure present, cutoff). The six-bucket accounting in `workings.json` has to sum to 33. | §3, §4, §8 |
| N2 NULL / 0 / absent | three different things, all present: FIL-023 is a filing with an empty amount (not 0), FY25-Q2's revision is a real `0.0` (not blank), FY23-Q4 is a covered period absent from the register entirely (`no_records`, not 0). | FIL-023, FY25-Q2, FY23-Q4 |
| N3 point-in-time | the whole task: two as-of answers per period, both partitioned by period, both bounded by a pinned cutoff. | §5 |

## Traps

| Trap | Where | Lazy algorithm it separates |
|---|---|---|
| Two vintages of one period, interleaved with other periods in filing order | FY24-Q1: FIL-004, FIL-014 | `MAX(as_of_date)` without partitioning by period |
| A restatement filed after the cutoff | FY24-Q2: FIL-030, 2025-12-02 | latest vintage = newest row, cutoff never applied |
| A vintage filed exactly on the cutoff | FY24-Q3: FIL-027, 2025-11-14 | `as_of_date < cutoff` instead of `<=` |
| A period whose only figures are preliminary | FY25-Q1 | promoting a provisional figure to final |
| A restatement that moves a figure upward | FY24-Q1: 8,000,000 → 8,180,000 | assuming restatements reduce, so the smaller vintage is the current one |
| The earliest filing of a period is an unaudited flash | FY24-Q1 FIL-003, FY24-Q4 FIL-011 | `MIN(as_of_date)` as the original vintage |
| A management-basis filing newer than every statutory one | FY24-Q3 FIL-028, FY25-Q2 FIL-024 | not filtering the reporting basis |
| A registered filing with an empty amount, newest in its period | FY24-Q4: FIL-023 | reading an empty cell as 0, or as the current figure |
| A covered period with no rows in the register | FY23-Q4 | conflating absent-row with zero, or omitting the row |
| An `under_review` period carrying two clean statutory vintages | FY23-Q3: FIL-001, FIL-019 | taking scope from the fact table instead of the close calendar |
| Every publishable vintage of a period filed after the cutoff | FY25-Q3 | one undefined reason code for two different causes |
| A revision percentage exactly on the rounding tie | FY24-Q1: 2.25 | the runtime's default half-to-even `round()` |

## Stated shape, graded shape

Every ordering and layout sentence the policy states is compared, so none of them is decoration:

| Stated in | Requirement | Graded by |
|---|---|---|
| §9 | one sheet named `Vintage_Report` | `artifacts.sheet_layout`, one of eight facts |
| §9 | the seven columns *in this order* | `artifacts.sheet_layout`, seven of eight facts, one per position |
| §3, §9 | rows in ascending period order | `artifacts.row_order`, fraction of rows in the right position, denominator `max(expected, got)` |
| §9 | `Period` spelled as in `close_calendar.csv` | `artifacts.row_order` compares the label as written |
| §9 | amounts with no currency symbol and no thousands separator | the amount comparison parses the cell strictly — `$8,180,000` is not a number |
| §9 | `Revision_Pct` not a percentage string, not a fraction | the rate comparison parses strictly — `2.3%` is not a number |
| §6 | `UNDEFINED` is the exact spelling | the sentinel comparison is case-sensitive — `undefined` is wrong |
| §9 | recorded values, not formulas | reported at the cell address, once per sheet; see *Known deviations* |

Measured against a copy of the answer key: sheet renamed `Sheet1` → 0.995, columns reordered → 0.969, rows descending → 0.958, amounts as `$8,180,000` strings → 0.792, `Revision_Pct` as `2.3%` → 0.896, sentinel lowercased → 0.812.

## Lucky-number check

The naive method: group `financials.csv` by period, newest filing wins, oldest is the original, no calendar, no basis filter, no cutoff, preliminaries promoted, empty amount read as 0, `round()` for the percentage. It writes a well-formed artifact — correct sheet, correct columns, correct JSON shape — and scores **0.365**, with `latest` at 0.111 and `revision` at 0.000. Its total is not the correct 46,922,000, and none of the five exclusion counts lands. The total depends on a tie-break the naive method never states: FY25-Q1 carries FIL-017 (7,655,000) and FIL-018 (7,700,000) on the same `as_of_date`, so first-match-wins (`idxmax`) gives **76,630,000** and last-match-wins (`sort_values().groupby().last()`) gives **76,675,000**. The reward is 0.365 either way — both figures are wrong for the same reason, and policy section 4 forbids the tie among *selectable* vintages, so the correct answer is untouched. It also loses on row order, because the period it leads with is out of scope.

## Known deviations

- **`Period` is the row key, so one wrong header there is charged five times.** Measured: renaming the header `Period` to `period_id` and changing nothing else scores `artifacts` 0.250, `definedness`/`latest`/`original`/`revision` 0.000 and `workings` 1.000 — **0.208** overall, because five of six dimensions locate their rows by that header. A wrong header on a single value column costs far less: misspelling only `Latest_Amount_USD` scores **0.822**. This is deliberate rather than accidental — policy section 9 fixes the spelling and `Format_Example.xlsx` shows it — but it does mean the dimensions are not independent of each other for that one column, and equal dimension weighting multiplies the error. Softening it means letting the row scan fall back to the first column when the `Period` header is absent, which would also stop grading the column order the same section states.

- **Formula cells are reported, not evaluated.** All four sheet graders load the workbook twice — `data_only=True` first, then a formula-bearing read — and fall back per cell, so a cell an agent wrote as `=ROUND(...)` is never silently scored as blank. It is named at its address instead, once per affected sheet: `revision_pct: Vintage_Report!F3 holds the formula '=ROUND((B3-D3)/D3*100,1)' and no cached value; policy section 9 requires recorded values, not formulas`. openpyxl has no formula engine and neither does the verifier, so evaluating them is out of reach; the policy states the values-not-formulas rule in §9 and the diagnostic names the cause. A workbook with all five defined `Revision_Pct` cells written as formulas scores 0.896 overall; one with every numeric cell written as a formula scores 0.688.
- Graders scan every sheet for the required header rather than trusting `.active`, so an empty `Sheet1` in front still grades correctly. The sheet **name** is graded separately, as one of the eight facts in the `artifacts.sheet_layout` fraction, so a report written to `Sheet1` scores 0.995 rather than 1.000.
- **Bucket-precedence coverage is incomplete at the lower ranks.** Rows exercise rank 1 over 2 (FIL-002), rank 1 over 5 (FIL-032) and rank 2 over 3 (FIL-028), but no row is simultaneously `after_cutoff` and `no_amount`, or `after_cutoff` and `preliminary`. Closing the gap means reseeding the register and re-deriving the key, which is a worse trade than a documented gap while the key is verified correct.

## Gates

```bash
python3 tasks/new_task.py lint tasks/generated/restatement-vintages      # ok
python3 tasks/new_task.py gate tasks/generated/restatement-vintages      # builds and runs the image
```
