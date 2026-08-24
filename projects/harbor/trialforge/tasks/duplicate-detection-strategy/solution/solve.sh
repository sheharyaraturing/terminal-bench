#!/bin/bash
set -euo pipefail
# ORACLE SOLUTION — the acceptance gate.
#
# Harbor runs this instead of an agent when invoked with `-a oracle`. Its output
# must satisfy every claim in tests/reward.toml. Every number below was recomputed
# from the eight CSVs at /data and from /data/db/turing.db; NOTES.md records how,
# so this file can be re-derived rather than trusted.

# Write to BOTH paths: /logs/agent is what a shared-mode run reads, /logs/artifacts
# is what the SEPARATE verifier reads (see task.toml [verifier].environment_mode).
mkdir -p /logs/agent /logs/artifacts

tee /logs/agent/final_answer.txt /logs/artifacts/final_answer.txt <<'EOF'
Verdict up front, in the first line as you asked: one deduplication rule cannot be
written safely for this warehouse, and asking for one was not a sensible request —
not because the tables are messy, but because three of the eight cannot tell you
whether an identical row is a mistake or a second thing that really happened. Two of
those three are the ones that actually contain repeats. So the rule you want would be
guessing on exactly the rows where guessing costs you data. What follows is the
census, the reason, and the eight-line policy I would defend instead.

1. WHERE THE DUPLICATES ACTUALLY ARE

Exact whole-row repeats, table by table. Three tables have them, five do not.

    hospital impact records      34 rows    23 distinct    11 duplicate rows
    trade ledger                111 rows   110 distinct     1 duplicate pair
    barber shop records          31 rows    29 distinct     2 duplicate pairs

    food and beverage records    80 rows    80 distinct     none
    crime records                71 rows    71 distinct     none
    weekly pet-care financials   52 rows    52 distinct     none
    fantasy sports roster        51 rows    51 distinct     none
    film list                    50 rows    50 distinct     none

Those five clean results are stated positively and deliberately: all 80 consumption
rows are distinct, all 71 crime rows are distinct, all 52 pet-care weeks are
distinct, all 51 roster rows are distinct, all 50 films are distinct. I did not go
hunting for near-matches or fuzzy matches to make those five look more interesting
than they are. They are clean on the test you asked for, which is exact repeats, and
that is the whole of what I have to say about them.

The barber shop finding is worth calling out because it is easy to miss. Two pairs,
at data rows 7 and 12 and again at data rows 18 and 29:

    Female, 27, barber 1, Haircut, $12.00, satisfaction 4, rating 4.4
    Female, 32, barber 1, Haircut, $12.00, satisfaction 4, rating 4.2

Warehouse-wide the total is 14 duplicate rows out of 480, leaving 466 distinct rows.
Most of that total sits inside the hospital table: 11 of the 14, with the other 3
spread across the trade ledger and the barber shop.

2. WHICH TABLES CAN PROVE A REPEAT IS A MISTAKE

This is the question that decides everything else, and it splits the eight tables
cleanly in two.

Four tables identify their records uniquely:

  - The crime records carry a case reference that is unique across all 71 rows. It
    runs from CRIME679 to CRIME750 — 72 slots for 71 rows, with CRIME717 absent, so
    the sequence has a hole in it but no collision. A duplicate case reference here
    would be unambiguously an error, and there are none.
  - The fantasy sports roster is unique on either of its two identifier columns; each
    holds 51 distinct values across 51 rows.
  - The film list is unique on title: 50 distinct titles, 50 rows.
  - The weekly pet-care financials are uniquely labelled by week, Week 1 through
    Week 52, one row each. That is a period label rather than an entity identifier,
    but the grain is one row per week and the label enforces it, so it works as a key.

For those four, deduplication is a solved problem: the key is the rule.

3. THE BARBER SHOP RECORDS HAVE NO KEY AT ALL

The barber shop table has 7 columns and not one of them is unique. I also checked
every pair of columns — all 21 combinations — and no pair is unique either. There is
no visit identifier, no ticket number, no timestamp, no date. Nothing in the row
records *when* it happened or *which* visit it was.

The consequence is not a technicality. Both duplicate pairs are same-gender,
same-age, same-barber $12.00 haircuts with identical satisfaction scores and
identical barber ratings. A returning customer's second haircut, or two customers of
the same age and gender in the same chair at the same price, produces byte-identical
rows. So I cannot tell you those four rows contain two errors, and neither can any
rule you write. Deleting them is a coin flip on real revenue.

4. WHY ONE GLOBAL RULE IS UNSAFE

Applied uniformly across all eight tables, full-row deduplication removes 14 rows out
of 480. On five tables it removes nothing. On the hospital table it does the right
thing. On the trade ledger and the barber shop records it removes rows that might be
real, and it does so silently and irreversibly — nothing downstream logs that a real
observation disappeared.

The consumption records deserve a mention here even though they are clean today. Their
only unique column is the event date, and a date is not a record identifier: two
customers buying the same item on the same day is an entirely ordinary event that
would produce an identical row. They are keyless in the same sense the barber records
are, and their current zero is an accident of how this extract happens to be shaped,
not protection. The moment a second reading lands on one of those dates, a global
rule starts eating real rows there too.

5. THE TRADE LEDGER DUPLICATE IS NOT CERTAINLY AN ERROR

Undercutting my own finding, because it needs undercutting. The single duplicate pair
in the ledger is two sell fills of 0.19565707 ETH at a spot price of 1533.25, both
stamped 2023-01-14 21:05:35 UTC, with identical subtotal, fee and total.

That is physically plausible. An order of that size filling twice inside the same
second is normal market behaviour, and this ledger records fills, not orders. There is
no trade identifier and no order identifier anywhere in its 9 columns, so nothing in
the data can settle whether this is one event exported twice or two events that
genuinely coincided. I am not going to call it a defect on the strength of it looking
like one. It goes to review, not to DELETE.

6. THE HOSPITAL DUPLICATES, BY CONTRAST, ARE CERTAINLY ARTEFACTS

The hospital impact records are keyless too: the quarter label is not a record
identifier — it repeats two to four times per label — so no column identifies a row.
That makes the hospital records the third table with no key, alongside the barber shop
records and the trade ledger. But this is the one place where the answer is still
unambiguous. A quarter label denotes a period, not an event. Two byte-identical rows for the same quarter — the same GDP
growth, the same beds per 1000, the same doctors per 1000, the same ICU capacity, the
same case rate and the same death rate — cannot be two independent measurements of
that quarter. Independent measurements of the same period differ. These do not, in
any column. That is a load run twice, and full-row deduplication is correct here.

7. THE POLICY, PER TABLE

Eight lines instead of one:

  - crime records — deduplicate on the case reference. Currently no-op.
  - fantasy sports roster — deduplicate on either identifier column. Currently no-op.
  - film list — deduplicate on title. Currently no-op.
  - weekly pet-care financials — deduplicate on the week label. Currently no-op.
  - hospital impact records — deduplicate on the full row. Removes 11 rows, 34 to 23.
  - trade ledger — do NOT auto-delete. Quarantine the pair to a review table and have
    a human confirm against the exchange statement.
  - barber shop records — do NOT auto-delete. Quarantine both pairs for review, and
    accept that the review may well conclude they are genuine visits.
  - food and beverage consumption records — no rule until it has an identifier. It
    passes today by luck, not by design.

8. THE TWO MISTAKES DO NOT COST THE SAME

Worth being explicit about, because it is what justifies the quarantine lines above.
A duplicate left in place biases an aggregate, and that is bad — but the row is still
there, so the finding is reversible the moment somebody notices. A row deleted because
a rule assumed it was a duplicate is gone; once the source load has aged out there is
nothing to restore it from and no record that it ever existed. Those are not
symmetrical errors, and a policy that treats them as symmetrical is wrong by
construction. Bias towards the recoverable mistake.

9. WHAT THE DUPLICATES ARE DOING TO THE PUBLISHED NUMBERS

The worked example on the worst offender, the hospital impact records, for the
steering group:

    mean deaths per 100,000      raw  19.59   ->   deduplicated  18.04   (down ~1.54)
    mean cases per 10,000        raw 905.88   ->   deduplicated 856.52   (down ~49.36)
    mean ICU capacity            raw  67.21   ->   deduplicated  67.83   (up   ~0.62)
    mean beds per 1000           raw   4.44   ->   deduplicated   4.91   (up   ~0.47)
    mean doctors per 1000        raw   2.53   ->   deduplicated   2.62   (up   ~0.09)
    mean GDP growth              raw  -3.73   ->   deduplicated  -3.68   (up   ~0.04)

Mind the directions: they are not all the same way. The two COVID rates both fall,
and the four resource and economic means all rise. The raw table OVERSTATES both the
death rate and the case rate, and UNDERSTATES ICU capacity, beds, doctors and GDP
growth. The duplicated rows happen to skew high on the death rate
and low on ICU capacity, so there is no single correction factor and no "duplicates
inflate everything" shortcut that gets both right. Anyone who computes one of these
and generalises the sign gets the other one backwards.

10. THE ONE-LINE FIX, ANSWERED STRAIGHT

No. Do not wrap every table in a distinct-rows view, and do not put SELECT DISTINCT
in the standard as a default. It is exactly the global rule this whole review argues
against: on five tables it is a no-op that costs a scan, on the hospital table it is
right by accident, and on the trade ledger and the barber shop records it silently
deletes rows that nobody can prove were duplicates. A rule that is wrong on the only
tables where it does anything is not a default worth having.

11. WHAT HAS TO CHANGE FIRST

Mint a record identifier for the tables that carry none, starting with the barber shop
records and the food and beverage consumption records, at the point of loading: a visit or ticket
reference for the former, a transaction reference for the latter. A surrogate key
generated at load time is enough; it does not need to mean anything. Once those exist,
a repeat is distinguishable from a second event by construction and the policy becomes
mechanical instead of a judgement call. Until they exist, any deduplication policy
written for those two tables is guessing, and I would rather the standard said so than
pretended otherwise.
EOF
