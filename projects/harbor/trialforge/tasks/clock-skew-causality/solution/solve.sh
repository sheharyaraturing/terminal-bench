#!/bin/bash
# ORACLE — must satisfy every criterion in tests/reward.toml. Write BOTH paths:
# a separate verifier only reads /logs/artifacts. Figures: GROUND_TRUTH.md.
set -euo pipefail
mkdir -p /logs/agent /logs/artifacts

tee /logs/agent/final_answer.txt /logs/artifacts/final_answer.txt <<'EOF'
Dario — the draft is blaming the wrong component, and the reason is that one of
the three hosts was keeping bad time. Here is the corrected account.

SCOPE

Three services' records of the same window, each rotated into four slices:
twelve files in all. Read whole, that is 1,701 lines from the edge service, 1,735 from the queue
worker and 1,490 from the primary database. No slice is complete on its own and
none of the counts below survives being taken off one of them, so everything
here is against each service's full rotation. Most of that volume is background
chatter — health probes, queue heartbeats, checkpoints, autovacuum, WAL writes,
pool gauges — and none of it carries a request identifier, so none of it can be
paired across services. What can be paired is 97 request identifiers, and every
one of those 97 appears in all three logs — none is present in only some — so
the requests themselves are what let the three records be stitched together.

1. THE RECORDED TIMES CANNOT BE TAKEN AT FACE VALUE

The database host's clock is wrong. The edge service's and the worker's agree
with each other exactly; only the database's disagrees.

  offset:     135 seconds, i.e. 2 minutes 15 seconds
  direction:  the database host is AHEAD — running fast
  correction: subtract 135 seconds from every timestamp in its log

It is a fixed constant, not drift and not jitter. Every one of the 105 database
records that carries a request identifier yields exactly 135.000 seconds — a
single distinct value across the whole 40-minute window — so one subtraction
corrects the entire file. Nothing has to be modelled and no record needs its own
correction.

2. HOW THAT NUMBER WAS PINNED DOWN RATHER THAN ESTIMATED

Nothing in any of the three logs carries an authoritative time reference: no
time-source line, no offset field, every stamp already in UTC. The only thing
that crosses hosts is the request identifier, so that is what the number comes
from.

For each database call the worker brackets the call: it logs the start and the
completion, both on the worker's own clock. The database logs exactly one record
for that same call. Taking the database record's timestamp against the MIDPOINT
of the worker's own window — the ordinary round-trip midpoint estimate — cancels
the network time in both directions and leaves the offset. Across all 105
request-bearing database records that estimate is 135.000 seconds every single
time, to the millisecond.

Two details matter for getting that exact figure rather than an approximation.

  - The pairing has to be per DATABASE CALL, not per request. Eight requests made
    two calls each — a first that hit the exhausted pool and a retry — and each of
    those calls has its own worker window and its own database record. Pair those
    at the request level and the two calls get crossed, which scatters the answer
    across several values for no reason other than the bookkeeping.

  - It has to be the midpoint, not one edge of the window. The cruder version,
    database timestamp minus the worker's start of call, gives 135.023 to 136.500
    seconds with a mean of 135.469 — the same answer to the second, and a useful
    cross-check, but a range rather than the number.

CHEAPER READS I TRIED AND REJECTED

  - Comparing the files' own extents. The first timestamps in the three files
    differ by 19.418 seconds and the last by 240.000 seconds. Neither is the
    offset. The reason is that the database's background chatter — checkpoints,
    autovacuum, pool statistics, WAL writes — covers a wider span of real time
    than the other two logs do, starting earlier and ending later, so the extents
    measure coverage rather than skew. This is the read I would expect the review
    to ask about, and it gives two wrong answers, not one.

  - Reading it as a timezone problem. It is not one. Every stamp in all three
    files is already UTC, no line in any file names a timezone, a time source or
    a clock, and 135 seconds is not any timezone's offset from anything.

  - Sorting each file and looking for lines out of order. A single-host file
    cannot show cross-host skew, and in any case only one line in one file is out
    of order — see section 5, where it turns out not to be a clock problem
    either.

The same midpoint estimator applied to the edge against the worker gives exactly
0.000 seconds on 96 of the 97 requests, which is how we know only one of the
three clocks is wrong. The 97th is dealt with in section 5.

3. WHAT THE UNCORRECTED TIMESTAMPS APPEAR TO SHOW

  23 requests were answered 502 by the edge; the first at 09:30:12.000
  31 connection-pool-exhaustion records in the database log, all of them against
     the `primary` pool; the first stamped 09:31:00.000 in the database host's
     own clock

Read straight off the page, the database's first pool failure is 48.000 seconds
LATER than the first 502. That reading says the edge gave up on its upstream
first and the database errors are the wreckage of queries nobody was waiting for
any more. That is what the draft says, and it is an artefact of the bad clock.

4. WHAT ACTUALLY HAPPENED

Subtract the 135 seconds and the order reverses. The first pool exhaustion
occurred at 09:28:45.000 — 87.000 seconds BEFORE the first 502, not 48 seconds
after it. The two readings differ by exactly the offset: 48 + 87 = 135.

Corrected sequence:

  09:28:45.000  database connection pool exhausted, request req-adad6c35
  09:28:45.900  worker records receiving a pool-exhausted response for that
                same request and retries it
  09:30:11.060  first worker database-call timeout — the retry budget is gone
  09:30:12.000  first customer-visible 502 at the edge

The single observation that makes the uncorrected reading impossible rather
than merely odd: for req-adad6c35 the worker recorded receiving a pool-exhausted
response at 09:28:45.900, while the database's own record of that request's
failure is stamped 09:31:00.000. As recorded, the effect precedes its cause by
roughly 134 seconds. A worker cannot report an error the database has not
produced yet. That is not an improbable ordering, it is an impossible one, and
it is the reason to correct the clock rather than to argue about which log to
trust. Corrected, the cause precedes the effect by 0.9 seconds, which is what a
real call looks like.

And the inversion is total, not marginal, and holds request by request rather
than only between the first event of each kind. For all 23 of the requests
answered 502, the corrected pool-exhaustion record for that same request
precedes the edge's 502 for it, by about 2.4 seconds in every case. Under the
raw timestamps that test puts the database first in 0 of the 23.

CUSTOMER IMPACT

23 customer requests were answered 502. That is what the outage cost us. It is
not the 31 pool-exhaustion records — several of those were absorbed — and it is
not the 8 requests below, which were retried and answered successfully.

ROOT CAUSE

Connection-pool exhaustion on the primary database host is the first failure and
the root cause. The exhausted pool is the one named `primary`; the host's
`readonly` pool is gauged throughout the same window and never saturates, so the
failure is specific to the primary write path and not a whole-host condition.

It had been failing for 87 seconds before anything reached a customer. What
absorbed that interval is concrete: 8 requests took a pool-exhausted response
from the database, were retried by the worker, and were still answered 200 by
the edge. Those 8 are the reason the first 87 seconds are invisible in the edge
log. When the retry budget ran out the failures surfaced as 502s.

RULED OUT: the edge service's upstream timeout firing first, with the database
errors as the downstream wreckage of abandoned queries. The corrected order rules
it out — the database was already refusing connections 87 seconds before the edge
returned anything to a caller, and per-request the database failure precedes the
edge's response every time. The edge timeout is not a cause here and not a
contributing cause; it is the mechanism by which an existing database failure
became visible. Do not put a timeout change in the action items as a fix.

5. THE ONE THING THAT IS OUT OF ORDER FOR A DIFFERENT REASON

Request req-8625f445 is the single request whose edge-to-worker pairing does not
agree: it is off by 1.340 seconds while the other 96 agree to the millisecond.
That is NOT a second bad clock and it is not part of the 135-second offset. Its
claim record carries a second attempt, a requeued marker and a requeue delay of
1340 ms, and the edge had already answered the caller — with a 202, an async
accept — before the worker ever claimed the job. It is an application-level
requeue. A clock difference would show up on every request equally; this shows
up on one.

It is also the reason the worker's log steps backwards in time in exactly one
place: that requeued claim line was flushed against the original enqueue point,
so it sits earlier in the file than its own timestamp warrants, and the line
following it is stamped 09:17:04.280 against the requeued line's 09:17:04.920.
The edge's log and the database's log are strictly ordered throughout — one
backwards step in one file, not a pattern. Keep it out of the skew evidence
entirely; it proves nothing about the clocks and it is not part of the incident.

WHAT I WOULD PUT IN THE REVIEW

Root cause: primary database connection-pool exhaustion, 09:28:45. Detection
lag: 87 seconds of invisible failure before the first 502, then 104 seconds of
customer impact across 23 failed requests. Action items: pool sizing and
saturation alerting on the primary pool, and get the database host's time source
fixed, because the 135-second error is the reason the first draft of this review
named the wrong component. Not an action item: the edge timeout.
EOF
