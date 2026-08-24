# Duplicate detection strategy — derivation and design

**Persona:** Data Quality Engineer
**Archetype:** census of a defect across all eight tables → refusal of the requested
global rule → per-table policy with the metric impact quantified
**Targets:** ~52 tool calls · 18 claims · 5 servers declared, 17 tools exposed
**Reward:** 18 claims, all likert 3-point, **no weights** — every claim counts the same.

No fixture. Every fact below comes from data already baked into
`turing-mcpatlas:0.0.3` — the eight CSVs at `/data` and the warehouse at
`/data/db/turing.db`. That is why `task.toml` sets `docker_image` rather than
omitting it: there is nothing to build. **If you ever add a fixture here you must
delete `docker_image`**, or `should_use_prebuilt_docker_image()` skips
`environment/Dockerfile` and the fixture silently will not exist at run time.

## The premise

The agent is asked for one deduplication rule to apply to every table in the
warehouse, and asked in the same breath whether that was a sensible request. It was
not. The counting half of the task is mechanical: three tables have exact duplicates
and five do not. The half that discriminates is what a duplicate *means* in a table
that has no key — and the two tables holding the least alarming duplicate counts are
precisely the two where a duplicate cannot be proved to be an error at all. The
failure mode this task is built to catch is an agent that produces an accurate census,
writes `SELECT DISTINCT` as the rule, and never notices that its own rule would delete
rows it has no evidence against.

## Ground truth

### Exact whole-row duplicates, all eight tables (recomputed here, pandas)

| Table | Rows | Distinct | Duplicate rows | Key situation |
|---|---:|---:|---:|---|
| `covid_19_impacts_on_hospitals` | 34 | **23** | **11** | `quarter` not unique — 2–4 distinct rows per label, 8 labels |
| `coinbasetradehistory` | 111 | **110** | **1 pair** | no trade or order identifier in any of its 9 columns |
| `barber_shop` | 31 | **29** | **2 pairs** | **no candidate key at all** — see below |
| `food_and_beverage_consumption` | 80 | 80 | 0 | only unique column is the event date |
| `crime_records` | 71 | 71 | 0 | case reference unique, CRIME679–CRIME750, CRIME717 absent |
| `pet_care_2023_weekly_financials` | 52 | 52 | 0 | week label unique, Week 1–Week 52 |
| `fantasy_sports` | 51 | 51 | 0 | both identifier columns unique, 51 distinct each |
| `top_movies` | 50 | 50 | 0 | title unique, 50 distinct |

Warehouse-wide: **14 duplicate rows out of 480**, leaving **466** distinct. 11 of the
14 sit in one table.

### The barber shop duplicates — the correction that reshaped this task

The catalogue's ground-truth table records `barber_shop` as having **0** exact
duplicates. It has **two exact duplicate pairs**, confirmed here:

| Data rows | Row |
|---|---|
| 7 and 12 | Female, 27, barber 1, Haircut, `$12.00`, satisfaction 4, rating 4.4 |
| 18 and 29 | Female, 32, barber 1, Haircut, `$12.00`, satisfaction 4, rating 4.2 |

`31 rows → 29 distinct`. Independently reproduced by `DataFrame.duplicated()` and by a
group-by over all seven columns.

It is also the only table in the warehouse with **no candidate key**: no single one of
its 7 columns is unique, and none of the 21 two-column combinations is unique either
(checked exhaustively with `itertools.combinations`). There is no date, no timestamp
and no visit identifier, so a repeat visit by a customer of the same age and gender to
the same barber for the same service at the same price is byte-identical to a
duplicated load. That makes the correction *better* than the catalogue value rather
than merely different: it hands claim 4 a case where the honest answer is "these
cannot be adjudicated", which is the reasoning the task is trying to test.

### The trade ledger pair

`2023-01-14 21:05:35 UTC`, `Advance Trade Sell`, ETH, quantity `0.19565707`, spot
price `1533.25`, subtotal `299.99`, total `298.19`, fee `-1.80` — at data rows 101 and
102. Two fills of one order inside the same second is ordinary; the ledger has no
order or trade identifier, so the data cannot settle it.

### The hospital worked example

| Metric | Raw (34 rows) | Deduplicated (23 rows) | Move |
|---|---:|---:|---|
| Mean deaths per 100,000 | 19.5882 | 18.0435 | **down** ~1.54 |
| Mean ICU capacity | 67.2059 | 67.8261 | **up** ~0.62 |

Opposite directions. Distinct-row counts per quarter label: Q1 2020 → 3, Q1 2021 → 3,
Q2 2020 → 2, Q2 2021 → 3, Q3 2020 → 4, Q3 2021 → 2, Q4 2020 → 3, Q4 2021 → 3. These
sum to 23, not 34.

## Difficulty design

Pass criteria, per the 2026-08-20 update: **GLM 5.2 must land 0.90–1.00**, which is
what proves the task solvable. For the two NVIDIA models — Nemotron 3.5 Lightning
NVFP4 and Nemotron 3 Ultra 550B — **0/3, 1/3 and 2/3 are all accepted**, so the
NVIDIA spread cannot fail this task and nothing here needs to be made harder.

Weights were removed in `3663ceb`; all twelve claims now count equally, so the five
listed below are the *design* pressure points rather than weighted ones. Each is a
place where the plausible answer is wrong:

1. **Claim 1 — three tables, not two.** The cheap census finds the 34-vs-23 hospital
   duplication immediately and the trade ledger pair with a little more work. The two
   barber pairs are in a small table with no date column, which is exactly the table
   an agent scans last and least carefully. A model that reports two tables scores the
   hospital and trade numbers and fails the claim.
2. **Claim 2 — the five clean tables, stated positively.** A negative finding the
   prompt explicitly warns against padding. Models that substitute fuzzy or
   near-duplicate findings for the clean result fail; so do models that lump the five
   together as "the rest are fine".
3. **Claim 4 — the keyless table.** Requires testing uniqueness of columns *and*
   column pairs, then drawing a conclusion about what the absence means. A model that
   counts the duplicates and stops has done the easy half.
4. **Claim 5 — the global rule is unsafe.** The task asks for one rule. Producing one
   is the compliant answer and the wrong one.
5. **Claim 6 — undercutting its own finding.** The sharpest of the five. The agent has
   just reported a duplicate in the trade ledger; the claim requires it to argue that
   the duplicate may not be a duplicate. Models rarely volunteer that unprompted,
   which is why the single nudge sentence is aimed here.

Claims 4, 5 and 6 are the ones expected to split a mid model across three runs. If the
task lands too easy, delete the nudge sentence identified below. If too hard, split
claim 5 into two claims of weight 1.0 — the "14 of 480" arithmetic and the keyless-table
argument — so partial credit can flow.

Every anomaly is naturally occurring in the upstream data. Nothing was planted.

## Tool surface

17 exposed across 5 servers, all genuinely usable. sqlite and filesystem are the
primary route; calculator, desktop-commander and cli-mcp-server are redundant-but-valid
routes (they can read the CSVs or do arithmetic). No code-execution server is exposed:
it is deliberately withheld so every count and mean has to be expressed as a query
rather than one pandas script, which is what carries the tool-call count. Distraction
is same-server near-misses plus these redundant paths - no far-field dead-end servers
are declared. Every declared server carries at least one exposed tool and every
exposed tool's server is declared.

Same-server near-misses and redundant routes, per `docs/TOOL_ALLOWLISTS.md` rule 2:

- `sqlite_read_records` — equality conditions only, so it cannot express
  `COUNT(*)` against `COUNT(DISTINCT ...)` or a group-by over every column.
- `sqlite_update_records` — a mutating sibling, tempting an agent to clean the
  duplicates it was asked to *report*. `sqlite_delete_records` is deliberately **not**
  exposed (rule 4: on this task of all tasks, a rollout that deletes duplicate rows
  destroys the ground truth mid-run). The withheld DELETE is discussed in the oracle's
  policy section as prose, which is not exposure.
- `cli-mcp-server_run_command` — no pipes and `/data` only, so the obvious
  `sort | uniq -d` is unavailable; still a real (slower) route to read the tables.
- `desktop-commander_read_file` / `_get_file_info` / `_list_directory` /
  `_start_process` and `calculator_calculate` — redundant-but-usable paths that read
  the CSVs or do the arithmetic a query would, so a model that takes them still makes
  progress. Not dead ends.

Dropped (dead ends, cannot touch the local data): `memory` (a knowledge-graph server
whose entities are keyed by name reads as a ready-made deduplication engine, but it
cannot read the tables), `ddg-search` (web search) and `whois` (domain lookup). None
can read the warehouse or CSVs, so they only work by server-name recognition, which
MCP-Atlas is designed to avoid.

## The removable nudge

One sentence in `instruction.md` sets up the hardest claim without answering it. As of the
2026-08-20 rewrite it is no longer aimed at the trade ledger specifically:

> "And wherever repeats do turn up, satisfy yourself they could not be two real things
> that both happened before you write them down as a defect."

Delete that sentence to make the task harder. It is the only place the prompt raises
the possibility that a duplicate is genuine on the trade side, and without it claim 6
requires the agent to undercut a finding it has just made, entirely on its own
initiative. The sentence is phrased conditionally — "if the trade ledger turns up
repeats" — so it does not disclose that the ledger has any, and it does not say which
way the question comes out.

It used to read "…satisfy yourself that two of those trades could not simply have
happened in the same second before you write them down as a defect", which supplied
claim 6's actual argument — same-second fills — rather than prompting the agent to
find it. The wording above asks for the same check without handing over the mechanism
or the timestamp.

Two other tells were demoted to neutral asks in the same leakage pass:

- The key paragraph used to end "…If there is nothing, say so plainly, because in that
  case a duplicated row and two real things that happened to come out identical are the
  same bytes on disk to us and no rule can tell them apart", which is the reasoning
  behind claims 4 and 5 written out in the prompt. It now reads "Name whatever you find
  and tell me what it can carry, and where there is nothing, say that plainly too" —
  the area (does a record identifier exist) without the consequence.
- The rule paragraph used to add "I would rather have eight short policies I can defend
  than one I cannot", which pushes the refusal that claim 5 scores. The conditional
  permission to refuse is the catalogue-mandated premise and stays; the editorial that
  told the agent which way to take it is gone.
- The worked-example ask used to say "be careful about the direction on each metric
  rather than assuming they move together", which telegraphs claim 10's
  opposite-directions finding. It now says "be careful about the direction each metric
  moves".

## Verified against the shipped warehouse

Originally derived from the eight CSVs — duplicate counts computed twice, by
`DataFrame.duplicated()` and by a group-by over the full column list; single-column
uniqueness for every column of every table; two-column uniqueness exhaustively for
`barber_shop`. All 17 `enabled_tools` names asserted present in `ci/tool_inventory.txt`
by script, and `sqlite_delete_records` asserted absent.

That derivation has since been re-run against the database the container actually serves.

Every figure above was recomputed from `trialforge/seed/turing.db`, which
`trialforge/seed/README.md` records as a byte-identical copy of what the image serves at
`/data/db/turing.db` (sha256 `8a395d3b…`, 8 tables, 480 rows, 72 columns). This closes the
gap left by the original derivation, which was done from the CSVs without booting a
container.

- Duplicate census, all eight tables: **8/8 match** — 480 rows, 466 distinct, 14 duplicate
  rows, 11 of them in the hospital table.
- The `barber_shop` correction holds: 31 rows → 29 distinct, two pairs. The catalogue's
  zero is wrong.
- `barber_shop` keylessness confirmed exhaustively: none of its 7 columns is unique and
  none of the 21 column pairs is unique (max 27 distinct against 31 rows).
- Hospital before/after: mean deaths per 100,000 19.5882 → 18.0435, mean ICU capacity
  67.2059 → 67.8261. Opposite directions, as claimed.
- Trade ledger pair confirmed at `2023-01-14 21:05:35 UTC`, `Advance Trade Sell`, ETH,
  `0.19565707`, spot `1533.25`, subtotal `299.99`, total `298.19`, fee `-1.8`.
- Crime references: 71 distinct, `CRIME679` to `CRIME750`, `CRIME717` absent.
- Pet-care week labels: 52 distinct, `Week 1` to `Week 52`.

Column names are now taken from the shipped database rather than reconstructed, but no
claim in `reward.toml` names a warehouse column regardless — keys and keyless tables are
described by role and by cardinality.

## Still not verified

- **No rollout has ever been scored.** The oracle has not been run, `nop` has not been run,
  and no model has been run. Every pass-rate statement in this file is design intent.
- `fantasy_sports` has **three** unique columns, not two: `player___no`, `team_id` and
  `contract__end_date`. Claim 3 speaks of "either of its two identifier columns" and now
  says explicitly that naming the third does not contradict it.

## Catalogue corrections carried into this task

- **`barber_shop` duplicates.** The spec block's ground-truth table says **0**; there
  are **two exact duplicate pairs** (data rows 7/12 and 18/29, 31 rows → 29 distinct).
  Claim 1 therefore says three tables rather than two and names the barber counts, and
  claim 2 lists **five** duplicate-free tables rather than six. An answer that found
  the barber pairs would otherwise have been scored down against a claim that was
  simply wrong. The correction also strengthens the task: because `barber_shop` is the
  only table with no candidate key, its duplicates are the one case where the honest
  verdict is "cannot be adjudicated from the data", which is what claim 4 now tests.
- **Spec claim 3, "three tables have a natural unique key".** Four do. The spec's own
  ground-truth row for `pet_care_2023_weekly_financials` notes its week label is
  unique (Week 1–52) and then omits it from the claim. Claim 3 names all four and
  distinguishes the week label as a period label enforcing a one-row-per-week grain.
- **Spec claim 4, "`barber_shop` and `food_and_beverage_consumption` have no candidate
  key".** True of `barber_shop`; loose for the consumption records, whose date column
  is in fact unique across all 80 rows. Claim 4 is therefore confined to
  `barber_shop`, and claim 5 states the consumption position accurately: its only
  unique column is an event date, which is not a record identifier, so the zero is an
  accident of this extract rather than protection.

## Overlap to watch when shipping

**1. `consumption-integrity-gate` — claim 10 restates the covid before/after means.**
The catalogue's mutually-exclusive table lists tasks 1 and 13 as conflicting on the
hospital 34-vs-23 duplication. This task's claim 10 restates that same before/after
pair as its worked example — mean deaths per 100,000 down 19.59 → 18.04 and mean ICU
capacity up 67.21 → 67.83, including the opposite-direction discriminator — so shipping
it alongside `consumption-integrity-gate` (claims 11 and 12) double-counts one
descriptive claim, and `quarter-grain-aggregation` claim 9 computes it a third time.
The discriminators do not overlap — this task turns on keys and on the meaning of a
duplicate, not on the duplication itself — but if the three are shipped together,
claim 10 is the one to drop. That task's NOTES nominates the same claim from its side,
and its claim 12 is weighted where this one is not.

**2. `dust-row-materiality` — claim 6 rests on the same single Coinbase duplicate
pair.** The pair is `2023-01-14 21:05:35 UTC`, ETH, quantity 0.19565707, spot 1533.25,
subtotal 299.99, fee −1.80: one pair of byte-identical rows, and the only duplicate in
the 111-row trade ledger. Three claims across the two files are built on it, weighted
on both sides:

| Claim | Task | Weight |
|---|---|---|
| Claim 6 — "even the trade ledger's single duplicate is not certainly an error" | this task | 1.0 |
| Claim 5 — "exactly one pair of fully identical rows … at adjacent positions" | `dust-row-materiality` | 1.0 |
| Claim 6 — the 299.99 / 298.19 / 1.80 / 0.195657 effect on the totals | `dust-row-materiality` | **2.0** |

An evaluation set carrying both tasks pays twice for finding and reasoning about one
pair of rows. The discriminators are not identical — this task asks *whether the pair
can be shown to be an error at all* given that the ledger carries no order identifier,
while that task asks *how much it moves the totals* and ranks it against the dust rows
— but the finding step is shared. **If both ship, drop this task's claim 6**, which is
also what `dust-row-materiality`'s NOTES nominates: the materiality comparison against
the dust rows is that task's entire subject and cannot be removed, whereas this claim
is one of twelve here and the keys-and-policy discriminators (claims 1, 2, 4 and 5)
survive without it. Dropping it takes this file to eleven claims, still inside the 8–15 band, and it also
retires the nudge sentence quoted above — if claim 6 goes, that sentence should go with
it rather than be left pointing at nothing.

## Revision log

**2026-08-20 — instruction and claim pass.** The prompt was rewritten for realism and to
close four places where it handed over an answer:

- Five near-equal paragraphs with `Start with… / Then give… / Finish by…` scaffolding
  became three uneven ones (90 / 207 / 129 words), matching the shape of the shipped
  `fee-sign-convention-audit` prompt rather than reading as a numbered work plan.
- *"put that in your first line and give me the per-table version instead"* → *"say so up
  front and tell me what it has to be instead."* Keeps the conditional permission the
  catalogue mandates; stops giving away claim 8's shape.
- *"the one that wraps every table in a distinct-rows view and calls it done"* → *"a
  blanket one liner that cleans every table at once and calls the problem solved."* Claim
  11 stays traceable but the agent must supply `SELECT DISTINCT` itself instead of being
  handed it and asked to agree.
- The trade-ledger nudge was generalised to all tables (see **The removable nudge**), so it
  no longer points at which table carries a contestable duplicate, and it drops the word
  "fills", which hinted at partial order execution.
- The counting unit was ambiguous: *"count the rows that are exact repeats of another row"*
  admits 11, 22 or 11-groups for the hospital table, and claim 1 only accepted one of them.
  It now reads *"how many rows you would be throwing away if you kept one copy of each"*.

Claims 1, 2 and 3 gained a recall allowance — the counts may appear anywhere in the answer
and need not be a single table — after the same omission repeatedly failed correct answers
on `fee-sign-convention-audit`. Claim 1 also now accepts pair phrasing and bare
row-plus-distinct counts as equivalent.

Both shell scripts were committed `100644` from the first commit and are now `100755`. Every
other task branch and the TEMPLATE ship them executable; this task was the sole exception.

**2026-08-20 — claim defect pass.** Seven defects found by auditing the twelve claims against
the shipped database, three of them by an independent second audit. Every fix widens what a
correct answer may say; none changes a ground-truth value.

- **Claim 10 could fail a correct answer.** It demanded deaths against ICU capacity, but the
  two headline COVID metrics both fall under deduplication — cases 905.88 to 856.52 and
  deaths 19.59 to 18.04 — while the four resource and economic means all rise. An agent
  quantifying the two published rates was correct and scored zero. The claim now carries all
  six means with their directions and accepts any correct subset.
- **Claims 3 and 5 applied opposite standards to identical evidence.** The pet-care week
  label (52 of 52) was mandated a usable key while the consumption date (80 of 80) was
  mandated not a record identifier. Claim 3 now accepts either verdict on the week label
  provided it is reasoned, and claim 5 says the two readings are consistent.
- **Claim 9 asked for something the prompt never did.** Nothing in `instruction.md` mentioned
  the cost asymmetry between leaving a duplicate and deleting a real row. A sentence was
  added to the prompt asking which mistake the requester would rather make.
- **Claim 7 overstated its certainty and punished consistent reasoning.** It rested on the
  quarter label denoting a period, but the table demonstrably holds three to five rows per
  quarter and carries no candidate key of its own, so an agent applying the report's own
  no-identifier standard and hedging was penalised. It now rests on six continuous measures
  agreeing to the last digit, accepts hedged phrasing, and explicitly does not penalise an
  answer that notes the table is itself keyless.
- **Claim 12 named "the two keyless tables", which is wrong under either definition.**
  Strictly, the consumption records have a unique date; loosely, four tables carry no record
  identifier. It now reads "at minimum the barber shop records" and credits naming the
  ledger, whose missing order identifier is claim 6's entire argument.
- **Claim 2 contradicted the prompt.** The prompt asks for one plain line per clean table and
  nothing more; the claim enumerated row counts. Those counts are now explicitly optional.
- **Claim 3's CRIME679 to CRIME750 range and absent CRIME717** are marked colour rather than
  required, since the prompt asks for no ranges or gaps anywhere.

Two suspicions were raised and dropped as false positives: claim 4's "same-age" reading
across pairs rather than within them, which the differing ratings make self-correcting, and
claim 8 omitting the consumption records from its policy list, which carries no penalty
clause and so cannot cost an answer any points.

**2026-08-20 — claim 6 dropped.** The trade-ledger claim ("even the trade ledger's single
duplicate is not certainly an error") is removed and `target_claims` is now 11.

It did not merely overlap `dust-row-materiality` (TF-010, PR #13 open, Ready for Review) — the
two graded the same pair of rows in opposite directions. That task's claim 10 requires the
duplicate be called "the actionable defect", and its claim 6 requires quantifying the effect of
removing it; this claim failed any answer that "reports that pair as a confirmed defect, or
that removes it without qualification". No single answer ever faced both, but the suite paid
twice for finding one pair and taught contradictory lessons about it. TF-010 is ahead of us and
the materiality comparison is its whole subject, so this side gives way.

The nudge sentence stays, contrary to the earlier note above. It was generalised on the same
day from "if the trade ledger turns up repeats" to "wherever repeats do turn up", so it now
serves claim 4's barber-shop reasoning and claim 7's quarantine policy rather than pointing
only at the ledger. Claim 7 still names the trade ledger for quarantine, which stands on its
own: the ledger carries no order identifier, verified against the shipped warehouse.

**2026-08-20 — claim 11 ordering clause trimmed.** The first two rollouts (Ultra 0.7727,
Lightning 0.4545, judge gpt-5.6-luna) both scored 0.5 on claim 11 for the same reason: the
clause "the recommendation must come before any policy is adopted". Ultra had explicitly
recommended a visit identifier for the barber shop and a trade identifier for the ledger,
which is the whole of what the claim asks, and lost half a point on where in the answer it
said so. The clause is now demoted — naming the identifiers is what scores, position does
not, and proposing per-table actions elsewhere is no longer treated as conflicting.

Those two rollouts otherwise show the task working. Both models recommended deleting the
trade-ledger and barber-shop duplicates rather than holding them for review, which is the
failure this task exists to catch, and both lost claim 7 for it; Lightning also called the
barber pairs high-confidence mistakes and lost claim 4. Both got the hospital means wrong on
claim 9, Ultra reversing the direction on four of the six. Those are genuine misses. The trap
still bites after claim 6 was dropped.

Both rollouts predate the claim 3 rescope, the claim 3 and 5 equivalence allowances and the
solve.sh update, so they understate what the current revision would score.

**2026-08-20 — claims 6 and 8 decoupled from the central verdict.** GLM 5.2 scored 0.8182
(9 of 11) on the fully current claim set, under the 0.90 floor the model pass criteria set for
it. All four of its losses were half credit and all four came from one decision: it recommended
deleting the barber-shop and trade-ledger duplicates instead of holding them for review.

That decision belongs to claims 4 and 7 and is correctly punished there. It was also costing
claim 6, which scores whether the hospital duplicates are artefacts — GLM's reasoning on that
table was exactly right, and it lost half a point only for not asserting exclusivity — and
claim 8, which scores whether the answer names the worse mistake, where GLM described the
undetectable loss but was marked down because its final policy did not follow through. One
error was being charged four times, worth 0.18 of the total.

Claim 6 now scores the hospital reasoning alone and says so. Claim 8 now scores whether the
direction is named, wherever it appears, and says that a later delete recommendation does not
retract it. Neither change lets a wrong answer pass: an answer that deletes the barber and
ledger duplicates still loses claims 4 and 7 in full, which is the discriminator.
