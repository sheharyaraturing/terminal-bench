# context-mesh/segment-suppression

Compute conversion rate by segment under the published suppression policy.

Nine segments, four hundred exported visits, and a metric definition that says when a rate may not be published. The arithmetic is a division; the task is deciding what goes in the denominator and what to write when the denominator will not carry a rate. Two of the nine segments have no eligible traffic at all, two more are under the publication threshold, one sits exactly on it, and one has a full base and zero conversions — so the agent has to keep four things apart that all look like "no number here": a real `0.00`, a base too thin to publish, a base of zero, and a segment that was never in the extract. The prompt is [instruction.md](instruction.md); every rule lives in `metrics/Definitions.md` inside the workspace.

- **Tools** — MCP servers `filesystem,terminal,excel,word,time`, local tools `claim_done`, all behind the one SSE gateway on `127.0.0.1:8765`.
- **Verifier** — four Reward Kit dimensions, all scored as fractions: `artifacts` (the required columns, the layout §9 states, and the workings keys), `segments` (all four figures for every segment row and the total, over `4 x max(expected, produced)`), `suppression` (the sentinel, the two reason codes, and the total's exclusion of suppressed segments), `workings` (sixteen leaves of the population accounting). The workbook is loaded twice — cached values, then formulas — so a sheet written through the `excel` server with `=ROUND(B2/C2*100,2)` in the rate cells still grades 1.000; every sheet is scanned for the header, so an empty `Sheet1` in front costs nothing. The evaluated subset is cell references, `SUM` over a range, `ROUND`/`ABS` and arithmetic — enough for the shapes a spreadsheet tool emits for this sheet. A conditional formula falls outside it, and the cell is then named in the log as the formula it holds — `Conversion!D2 holds the formula '=IF(...)' and no cached value` — rather than reported as a blank, so the failure reads as the values-not-formulas rule §9 states rather than as a phantom empty cell.
- **No free points for an empty shell** — every `artifacts` criterion refuses a stub: the workbook must carry at least one data row under its header, and `workings.json` must have had §10's zeros replaced with figures. A headers-only workbook next to the unfilled §10 placeholder scores **0.000** overall, not the third of the reward a bare existence check would have paid. There is no `file_exists` criterion; the three shape criteria already return 0 when a file is absent.
- **The layout §9 states is graded** — `artifacts.output_layout` scores the sheet name, the header row, the column order and the row order, the last as the fraction of rows sitting in the ascending-`segment_id`-then-`TOTAL` position, against the key's own layout. §9 demanded all four and nothing measured them: the table is keyed by segment everywhere else, so a shuffled workbook used to score 1.000.
- **Everything else** — environment, gateway and eval chain are the suite template's, unmodified. See `docs/task-structure/`.

```bash
python3 tasks/new_task.py lint tasks/generated/segment-suppression
python3 tasks/new_task.py gate tasks/generated/segment-suppression
```

## Gate results

| Strategy | Reward | Detail |
|---|---|---|
| oracle | **1.000** | `artifacts=1.000 segments=1.000 suppression=1.000 workings=1.000` |
| nop | **0.000** | `artifacts=0.000 segments=0.000 suppression=0.000 workings=0.000` |
| naive | **0.383** | `artifacts=0.962 segments=0.136 suppression=0.182 workings=0.250` |
| headers-only stub of both outputs | **0.000** | `artifacts=0.000 segments=0.000 suppression=0.000 workings=0.000` |

The naive method is the lucky-number check: group `events.csv` by `segment_id`, count rows, publish when the count is greater than 30, suppress with a blank cell and one reason code, round with the language's own `round()`. It produces a well-formed workbook and lands 0.383 — its `artifacts` score is no longer a clean 1.000 either, because deriving the segment list from `events.csv` puts `S14` and `SX3` in the sheet and drops `S07`, which leaves six of eleven rows in the position §9 gives them.

## Undefined round-trip

Every near-miss form of "undefined" was graded against the answer key to confirm it is rejected rather than quietly accepted, and two correct-but-differently-written workbooks were graded to confirm they are not punished.

| Answer handed to the verifier | Reward |
|---|---|
| the key itself | **1.000** |
| the key with rates as `=ROUND(B2/C2*100,2)` and the total as `=SUM(...)` | **1.000** |
| the key behind an empty `Sheet1` | **1.000** |
| undefined rate rendered as `0` / `0.00` / `""` / a blank cell / `null` / `N/A` | 0.892 each |
| undefined rows omitted altogether — the missing-key form | 0.769 |
| `LOW_BASE` and `NO_BASE` interchanged | 0.942 |
| one `SUPPRESSED` code for both causes | 0.942 |
| threshold read as `> 30` | 0.877 |
| banker's rounding on the tie | 0.994 |
| every rate cell as `=IF(Cn>=30,ROUND(...),"UNDEFINED")` — outside the evaluated subset | 0.826 |
| the 29-base segment published at 72.41 | 0.958 |
| the key with its rows reversed | 0.979 |
| the key on a sheet named `Sheet1` | 0.979 |
| the key under a title row, header on row 2 | 0.979 |
| the key with `Numerator` and `Denominator` transposed | 0.992 |
| headers-only workbook and the unfilled §10 workings placeholder | **0.000** |

## Difficulty budget

| Lever | Instance |
|---|---|
| L1 overlong observation | **Not instantiated under the suite's default agent.** One vector: `data/events.csv`, 399 rows, measured at 18,161 chars rendered — a fifth of the Toolathlon agent's 100,000-char ceiling (`MAX_SINGLE_TURN_RETURN_CHARS`, the loop's own log line); Harbor's built-in agents truncate near 8–10 KB, but they never reach the MCP gateway and this suite is not measured under them, so it arrives whole in one call. The image carries ripgrep and the `terminal` server, and `Definitions.md` §2 states the navigation path — filter and aggregate at the shell, do not read the file whole. |
| L2 observation floor | four observations: `metrics/Definitions.md`, `metrics/Format_Example.xlsx`, `data/segments.csv`, `data/events.csv`. Premature-stop lure: `events.csv` looks like a complete enumeration of the segments, so a run that never opens `segments.csv` loses `S07` entirely and carries `SX3` and `S14` as if they were segments. Second lure: the workbook looks like the deliverable and `workings.json` gets dropped. |
| L3 prior contradiction | five, each written as *prior → what the environment says*. (1) A cohort with no data scores 0% → it is `UNDEFINED` with `NO_BASE`. (2) Division by zero and a thin sample are both "can't publish" → they are two reason codes and must not be interchanged. (3) A suppression threshold of 30 excludes 30 → a denominator of exactly 30 is published. (4) "Two decimal places" means the language's `round()` → the mode is half-up, and one rate lands exactly on the tie. (5) Rows with no recorded outcome drop out of the calculation → they stay in the denominator and out of the numerator. |
| L4a parameter/resource strictness | four lookups no constructed guess survives: the threshold `30`, the sentinel spelling `UNDEFINED`, the reason codes `LOW_BASE` / `NO_BASE` / `OK`, and the five exclusion bucket names in `workings.json`. All four exist only in `metrics/Definitions.md` and `metrics/Format_Example.xlsx` — the sheet name and column order are the output contract and are stated in the prompt. The exclusion accounting must additionally balance against `rows_read`, which no guess does. |
| L4b tool-name confusability | two unrelated servers declared: `word` (the workspace holds no `.docx` and the read-only server could not write one anyway) and `time` (every date in the task is pinned in `Definitions.md`; reading the clock can only introduce error). |
| L5 state distractors | 44 ineligible rows against 355 eligible, about 1:8 — 7 replayed `visit_id`s, 5 rows on unregistered segments, 9 outside the period, 9 internal-channel, 14 voided. Two of the nine registered segments carry no eligible traffic (`S06` has ten rows, none eligible; `S07` has none at all) and two segment ids that appear only in `events.csv` (`SX3`, `S14`) are not segments. |
| L6 restraint | `S04`: denominator 29, numerator 21. A 72.41% conversion rate is sitting there fully computable, one visit short of publishable, and the correct output is `UNDEFINED` / `LOW_BASE`. Nothing in the data resolves the shortfall; the policy says flag it. |
| N1 population assembly | the denominator is derived from `Definitions.md` §3, never handed over: five inclusion tests, an attribution precedence for rows failing more than one, and an excluded-row accounting that must balance against the row count. |
| N2 null / definedness | strong, and the point of the scenario: an empty `outcome` is a visit whose result is missing, not a non-conversion (denominator yes, numerator no); a denominator of 0 is `NO_BASE`; a denominator of 1-29 is `LOW_BASE`; `S08` shows a genuine `0.00` that must not be confused with either. Absent-row (`S07`), all-rows-ineligible (`S06`) and real-zero (`S08`) are three different dispositions. |
| N3 as-of correctness | not carried — waived under Waivers below, with the reasoning. |
| Traps | six, below |

## Traps

| Trap | Where | Lazy algorithm it separates |
|---|---|---|
| Denominator exactly 30 | `S03`, 11/30 → 36.67 / `OK` | `> 30` instead of `>= 30`. Suppressing `S03` costs its row, both its contributions to the total, and the total's rate. |
| Denominator 29 with a spectacular rate | `S04`, 21/29 → would read 72.41% | reporting the figure because it is the most interesting number on the sheet. The restraint case. |
| Denominator 0 through two different routes | `S06` (ten rows, none eligible) and `S07` (no rows at all) | conflating division-by-zero with small-sample suppression — a single `SUPPRESSED` code, or `LOW_BASE` on a zero base. Also catches deriving the segment list from `events.csv`, which drops `S07` entirely. |
| A suppressed segment inside the total | `S04` and `S05` carry 24 conversions over 41 visits | totalling every row. Including them moves the pooled rate from 22.93 to 27.04. |
| A rate exactly on the rounding tie | `S02`, 5/32 → 15.625 | round-half-to-even, which is what `round()` and most defaults do. Half-up gives `15.63`, banker's gives `15.62`. |
| Eligible visits with no recorded outcome | 32 rows across seven segments, 3 of them in `S03` | dropping unrecorded rows from the denominator as well as the numerator. Doing so takes `S03` from 30 to 27 and suppresses a segment that should be published, and overstates every other rate. |

A seventh case is not a trap but the control that makes the sentinel meaningful: `S08` has 41 eligible visits and no conversions, so its published rate is `0.00`. An implementation that renders suppression as zero cannot tell `S08` from `S04`.

## Waivers

**N3, as-of correctness.** Not carried. The catalog's coverage matrix marks N3 `—` for G2, and every date in this scenario is pinned by `Definitions.md` rather than resolved as-of a record's own date, so there is no value-in-force to look up. The point-in-time discipline that remains is that the reporting period comes from the document and not from the clock or from the extract's date range, which is what keeps the answer stable under the calendar. Nothing else on the difficulty budget is waived.
