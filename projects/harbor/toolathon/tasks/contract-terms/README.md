# context-mesh/contract-terms

Set each open invoice's due date from the governing contract clause or the AP manual.

Twenty-five invoices need a due date and a citation for it. The AP manual states a net-30 default a page in and, in the same breath, that executed contract terms displace it — so the whole task is deciding, invoice by invoice, whether a document in `contracts/` actually governs. That decision needs three facts the environment does not hand over: the supplier's registered legal name (invoices carry trading names, contracts carry entities, and the register in the manual is the only bridge), whether the contract's validity window contains the invoice's own date, and whether an amendment moved the terms partway through the period. The fifteen supply contracts in `contracts/` run to about nineteen thousand characters each with the payment clause past the eight-thousandth, so none can be read whole; two further documents there set no payment period at all, six contracts belong to suppliers with no open invoices, and one supplier holds two live contracts that disagree and must be flagged rather than resolved.

The counter-intuitive part is that net-30 is right for eleven of the twenty-five invoices and wrong for the rest — an agent that trusts the default, and an agent that trusts the first contract it finds bearing a similar name, land on different wrong answers.

- **Tools** — MCP servers `filesystem,terminal,excel,word,time`, local tools `claim_done`, all behind the one SSE gateway on `127.0.0.1:8765`. `word` is read-only, which is fine: nothing here writes a `.docx`. `time` is declared and unused — the run date is fixed in the manual, and an agent that reaches for a clock has already gone wrong.
- **Verifier** — three dimensions, five criteria, all fractional. `tests/artifacts/check.py` carries three: `schedule_shape` wants the worksheet manual clause 7.1 names, the four columns in the order clause 7.2 fixes *and at least one data row beneath them*, so a headers-only shell scores zero rather than banking the dimension; `row_order` grades clause 7.3's ascending-Invoice requirement positionally, as the fraction of rows sitting where they belong; `vendor_labels` compares the trading name clause 7.4 fixes. `tests/duedate/check.py` scores due dates against `tests/expected/payment_schedule.xlsx` and `tests/sourcing/check.py` the governing document and clause. Every grader scans all sheets for the header rather than trusting `.active`, loads the workbook twice so a formula-written cell is reported as its formula — once per sheet, naming the cell and clause 7.6, not once per cell — and divides by `max(len(expected), rows_written)` so padding cannot inflate a score. For the two flagged invoices, `None`, `""`, `0` and an absent row all normalise to something that is not the reason code — asserted at grader import. No criterion pays for the file merely existing.
- **Everything else** — environment, gateway and eval chain are the suite template's, unmodified. See `docs/task-structure/`.

## Generating

```bash
```

## Difficulty budget

| Lever | Instance |
|---|---|
| L1 overlong observation | **Not instantiated as a truncation lever under the suite's default agent.** One vector: the 15 supply contracts in `contracts/`, measured at 19,667 chars of extracted text at the largest, with the payment clause 8.3–13.4 KB in — well inside the Toolathlon agent's 100,000-char ceiling (`MAX_SINGLE_TURN_RETURN_CHARS`, the loop's own log line); Harbor's built-in agents truncate near 8–10 KB, but they never reach the MCP gateway and this suite is not measured under them, so any one contract arrives whole. What remains real is the breadth: fifteen documents is fifteen calls, which is an L2 observation floor rather than an L1 ceiling. Navigable: the header block sits on the first page, clause 4.7 of the manual gives the search string for the payment sentence and warns that its clause number is neither constant across contracts nor the one the first-page clause list gives for Invoicing and Payment, and `terminal` is available for scripted extraction. |
| L2 observation floor | 33 invoice rows + 18 supplier documents + the manual's seven clauses and register ≈ 60 observations. The floor is per supplier, not per invoice: nine suppliers hold open invoices, so a per-invoice search repeats work 25 times instead of 9. |
| L2 lure | Clause 4.2 states net-30 plainly, one page in, and covers every invoice on its face. A run that stops there produces a full 25-row schedule that looks finished and scores 0.44 on content. |
| L3 prior contradiction | Prior: net-30 is the industry default *and* the manual's own stated rule → what the environment says: clause 4.1 subordinates it to any executed contract, and only 11 of the 25 invoices end up on net-30. Twelve are governed by a contract or amendment clause and two are unresolvable. |
| L4a parameter/resource strictness | The payment clause number varies by contract (`6.4`, `8.3`, `8.5`, `9.4`, `10.2`) and cannot be guessed from the clause list. Contracts are executed in registered legal names (`Ashgrove Speciality Chemicals plc`, `Meridian Laboratory Supplies Ltd`); invoices carry trading names (`Ashgrove Chemicals`, `Meridian Lab Supplies`). Exact lookup returns not-found and substring lookup misses those two while mis-hitting `Meridian Freight Ltd` and `Northwind Energy Ltd`. The register in manual clause 3 is the only bridge; guessing the entity is not possible from the invoice sheet. |
| L4b tool-name confusability | Five servers declared, `time` unrelated to the work — the run date is pinned in manual clause 1.2 and the manual forbids the clock. `word` is read-only and only ever reads. |
| L5 state distractors | Documents: 10 of 18 set no in-scope answer — 6 contracts for suppliers with no open invoices, 1 contract expired before every invoice it could touch, 1 renewal that has not commenced, 1 NDA, 1 SOW — leaving 8 that do, a ratio of 5 irrelevant to 4 relevant. Rows: 8 of 33 invoice rows are out of scope (4 `Paid`, 2 `Cancelled`, 2 `Open` but dated after the run date), roughly 1 irrelevant to 3 relevant. |
| L6 restraint | `Vantage Facilities` holds `CON-2025-007` (45 days) and `CON-2025-062` (14 days), both in force on both invoice dates, with no amendment or supersession marker on file. Clause 6.1 requires `REVIEW` / `REVIEW-CONFLICTING-TERMS`; picking either contract, or falling back to net-30, scores zero on both cells. Two invoices, 8% of the schedule. |
| Traps | 6, table below. |

Boundaries carrying a record: an invoice dated exactly on the run date (`INV-26-130`, in scope); one dated exactly on a contract's expiry date (`INV-26-120`, contract governs); one dated exactly on a contract's commencement date (`INV-26-116`, contract governs); one dated exactly on an amendment's effective date (`INV-26-109`, amendment governs); eight due dates landing on a Saturday and two on a Sunday, all rolled to the Monday under clause 5.2.

## Traps

| Trap | Punishes | Cost when it bites |
|---|---|---|
| 11 of 25 invoices genuinely fall to the manual's net-30 default | reading clause 4.2 and stopping — the answer looks complete | 0.44 content (the naive method) |
| `Corvid Logistics` holds `CON-2022-018`, expired 31 Dec 2025, and `CON-2026-009`, commencing 1 Apr 2026; every open invoice sits in the gap. `Meridian Lab Supplies` has one invoice inside its contract's window and one two days after it expired | "the supplier has a contract, so use it" — ignoring validity windows | 0.72 content |
| `AMD-2026-002` replaces `CON-2024-033`'s 60-day clause with 20 days from 2 Feb 2026; two Ashgrove invoices fall either side | reading only the first matching document, or taking the newest contract wholesale | 0.92 content |
| `NDA-2025-011` and `SOW-2025-042` are the only documents on file for `Kestrel Analytics`, and both state periods in days that are not payment terms | treating every document in `contracts/` as a terms source | 0.92 content |
| `Vantage Facilities` holds two live contracts stating 45 and 14 days with nothing to separate them | guessing between two equally good candidates instead of flagging | 0.92 content |
| Every contract states notice, rejection, dispute and price-review periods in days before the payment clause; trading names collide with two unrelated registered entities | first-`(NN) days` regex extraction, and fuzzy vendor-name matching | 0.80 content (register bypass); 0.52 overall for a combined fuzzy-match-plus-first-number run |

No decoy announces itself. Manual clause 4.7 identifies the payment provision positively — the sentence stating when the Buyer shall pay a correctly rendered and undisputed invoice — and does not enumerate the notice, rejection, dispute and price-review periods it is not; each of those sentences says what it is about, so the exclusion is read off the document rather than handed over. Clause 4.6 turns on the Document Type printed in each header block and no longer adds that the periods in the NDA and the SOW are not payment terms. Clause 7.7 points at `Format_Example.xlsx` for the shape and no longer says its row is not an answer: the row cites `INV-00-000`, a supplier absent from the register and `CON-0000-000`, none of which exists, and clause 1.3 scopes the schedule to the rows of `open_invoices.xlsx`.

Ablation figures above are the fraction of the 25 rows still correct when that rule alone is dropped from the oracle. Dropping the weekend-roll rule of clause 5.2 alone costs 0.40; using the system clock instead of the pinned run date adds two out-of-scope rows and costs 0.07.

## Gates

```bash
python3 tasks/new_task.py lint tasks/generated/contract-terms
python3 tasks/new_task.py gate tasks/generated/contract-terms
```

## Graded requirements

Every layout rule the manual states is measured, and nothing is stated that is not: clause 7.1's sheet name is looked up by name, clause 7.2's column order is scored as the fraction of the four headers standing in the right position, clause 7.3's row order as the fraction of rows standing in the right position, clause 7.4's Vendor by comparison, clause 7.6 by the formula-bearing second read. Clause 5.3 asks for the `YYYY-MM-DD` form, which the due-date normaliser compares, and no longer asks for it "as text", which it does not; clause 6.1 no longer asks for upper case, which the sourcing normaliser folds away.

## Waivers

None. One restraint case, as the checklist requires — clause 6.1's `REVIEW` is defined for that case and clause 6.2 names the four near-miss situations (no document, expired, not yet commenced, no period stated) that resolve to clause 4.2 instead, so the sentinel's scope is stated rather than left to inference.
