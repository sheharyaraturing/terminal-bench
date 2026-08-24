# NOTES — clock-skew-causality

## Premise

A Site Reliability Engineer has to write the incident review for a checkout
outage. Three services each kept their own record of the window, and read at face
value the edge service returns its first 502 forty-eight seconds *before* the
database logs its first connection-pool failure — which says the edge gave up
first and the database errors are the wreckage. That is the draft, and it is
wrong.

Layer 1 is that one host's clock is 135 seconds fast. A shallow pass gets there:
the numbers do not line up, the database's records look late for everything.

Layer 2 is what the correction does. Subtract 135 seconds and the pool failure
lands 87 seconds *before* the first 502 — the causal order inverts and the root
cause changes hands. That finding cannot exist until the offset has been
established and applied, which is what makes the layering structural rather than
rhetorical: a model that reports "the clocks disagree" and stops has produced a
true observation and the wrong incident review.

The decoy is a request that genuinely is out of order for a different reason: an
application-level requeue. It contributes a 1.34-second discrepancy on exactly
one request, and it is the reason the worker's log steps backwards in time once.
A model that folds it into the clock story reports two bad clocks instead of one.

The offset is recoverable **only** by pairing on shared request identifiers. No
log line names a clock, a time source, a drift, or any timezone other than `Z`,
and the cheap shortcut of comparing the files' own extents returns the wrong
number by construction — the database's background chatter deliberately covers a
wider span of real time than the other two logs, so first-timestamp and
last-timestamp comparisons give about 19 s and about 240 s.

## What this task is scored for

This task exists to produce a **graded** signal, not a pass/fail one. Three runs
of one model should land at visibly different scores, and the difference should
come from what the model actually established rather than from judge noise. Two
consequences run through every design decision below.

- **A criterion that every model earns, or that no model earns, is dead weight.**
  It moves the mean and contributes nothing to the spread. The audit trail on
  this task is mostly the story of finding and fixing those: see *Claim history*.
- **A criterion must be losable for a reason the answer is responsible for.**
  Losing a point to a judge's sensitivity to word order is noise, and noise in
  the reward is worse than an easy claim. Criteria 5 and 3 both carry explicit
  tolerances for that reason.

The corpus is sized to the same end. It is large enough and split finely enough
that counts have to be computed rather than seen, so the counting criteria fail
for a real reason, and small enough per slice that nothing collapses into a
truncation accident.

## Fixture provenance

The three services' logs are **synthetic and authored here**. Nothing was
downloaded and no real telemetry was used.

Each service's record is **rotated**, the way a host actually hands logs over:
`<svc>.log` is the newest slice and `<svc>.log.N` the oldest. Concatenated
oldest-first, the slices of a service are one continuous record with no gap and
no overlap. Four slices per service, twelve files, all injected by `COPY` to
`/data/logs/`.

| artefact | lines | bytes | sha256 |
|---|---:|---:|---|
| `logs/api.log.3` | 426 | 47,546 | `ca032f8dd4cdec4696861f11bc5e681bec8dcadcc01e3bfa168509eafa5345ef` |
| `logs/api.log.2` | 426 | 47,564 | `61cbe2cdfed1365eacd2663670ccd38fa35602c63ed1d3c4f26f89ea9787f229` |
| `logs/api.log.1` | 426 | 47,653 | `68e28ad7ba1d612765b21cc1aa29ddbb907da8f7b7e174e69081445ea33a417e` |
| `logs/api.log` | 423 | 47,834 | `fe6204ff2b7b65406c073b9badbc6215d92f7489432fc26badd0bbc6a6f6aa5a` |
| `logs/worker.log.3` | 434 | 48,172 | `cac15cb845341518fe50da53c5a7bee258c377d2619dc81b07c4144167a1bc3d` |
| `logs/worker.log.2` | 434 | 48,176 | `32ee5a34a15398deac07f4d9af0b0ae400040792c4a0a7be9c6217855b51b9aa` |
| `logs/worker.log.1` | 434 | 48,869 | `09784d5d6a754a182868e68b2ec6ef815a91871b8438c57d1020d5bbe3c72efd` |
| `logs/worker.log` | 433 | 48,677 | `17eacb38bd66821200485a69941aea369d90fe671d6f12269148ed7c790758d4` |
| `logs/db.log.3` | 373 | 42,197 | `e5c8ffa53df724060edb7f11a2b5d830f7a7eba6522953dcb51468b3c3e2be32` |
| `logs/db.log.2` | 373 | 42,234 | `d68af5ca5aa0c8416901da52c90c5bb3fb9e704013577477d4b79e6678ac126e` |
| `logs/db.log.1` | 373 | 42,791 | `83720dae258884d4258deae19183fc25a2e8a0bdb38f804723fb6f82eb5b13ad` |
| `logs/db.log` | 371 | 42,431 | `7efb1f3743832e72e2f70bd6b714fbdc805afd9aeb06c6edd6167cb1deb9dffd` |

Per service: `api` 1,701 lines / 190,597 bytes, `worker` 1,735 / 193,894, `db`
1,490 / 169,653. `fixtures/GROUND_TRUTH.md` is 7,238 bytes and is an authoring
artefact — it is **not** injected.

Build invocation:

```
bash environment/fixtures/build_fixture.sh
```

It was actually run. Determinism was verified by copying the script alone into an
empty directory, re-running it, and diffing the whole `logs/` tree plus
`GROUND_TRUTH.md`: all thirteen files reproduced byte-for-byte. The only entropy
source is `random.Random(20241114)`, consumed in a fixed order, and it is used
only for filler — request identifiers, routes, client addresses, statement names,
row counts, queue depths, WAL segment names, buffer counts. Every instant a claim
asserts is a literal: the first 502 is anchored at `09:30:12.000` and the first
pool failure at `09:28:45.000` true time, and the eight retry-absorbed requests
and twenty-three failed requests are laid out from fixed tables. All arithmetic is
in integer milliseconds, so the midpoints are exact and the offset comes out to
`135.000` rather than to a float artefact.

No pinned SHA — this task ships no git fixture. No warehouse table is touched at
all: the eight baked tables in `turing.db` are untouched because this task never
writes to it.

### The size band, and why it is asserted in the Dockerfile

`task.toml` sets `tool_output_cap = 60000`. The build asserts two things about
that ceiling and fails if either breaks:

- **every slice is under it** — the largest is 48,869 bytes against the 60,000
  ceiling — so any one slice can be read whole in one tool result. Nothing here turns on an agent noticing a truncated read, which would
  be a cliff rather than a gradient: an agent that mishandles truncation scores
  near zero and tells us nothing.
- **every service's rotation is far over it** — 191 KB, 194 KB, 170 KB against
  60 KB — so no service can be read in one call and no single file contains a
  service's own record. A count taken off one slice is a count of that slice.

That band is what makes the counting criteria (23 requests answered 502, the
inversion across all 23, the 8 absorbed) fail for a reason the answer owns.

**Why the ordinary traffic was not scaled.** The obvious way to grow the corpus is
more requests, and it is wrong here. Sixty-four ordinary requests on a 35 s grid
already put a handful of successful primary-database executions inside the
09:28:45–09:31:56 window. Multiply the traffic and that becomes dozens of
successful writes during a total pool exhaustion, which is a genuine
contradiction: a model could reasonably argue the pool was never exhausted and
undermine the root-cause criterion. The volume therefore comes entirely from
background series that carry no request id — health probes across six upstreams,
heartbeats across six queues, WAL writes, pool gauges, checkpoints, autovacuum,
bgwriter. None of it can be paired across services, none of it changes a scored
value, and none of it contradicts the story.

**Why the extents survive the scaling.** Every background series is pinned at
both ends. The api probes run 09:00:20 to 09:39:20 and the worker heartbeats
09:00:10 to 09:39:40 on their own clocks; every database series runs true
08:58:05 to 09:41:05, i.e. recorded 09:00:20.000 to 09:43:20.000. Those four
instants are what the 19.418 s and 240.000 s of criterion 15 are measured from,
and each series' step divides its span exactly. A series may change its cadence
or its cardinality but must not change its first or last tick.

**Why the worker's load surge starts at 09:29:10, and ends at 09:33:30.** The
worker's clock needs no correction, so a heartbeat carrying a large queue depth
before the corrected first pool exhaustion at 09:28:45.000 would make the worker
backlog a defensible first failure — which is not the story the criteria score.
The hot window therefore opens 25 s after the database failed, and closes 75 s
after the pool recovers, because a queue keeps draining once its dependency is
back.

Those two margins are deliberately **unequal**, and that is load-bearing. The
database's own saturation gauge is hot over true 09:28:45–09:32:15, i.e. recorded
09:31:00–09:34:30. Align the two hot windows instead of pairing on request id and
the starts differ by 110 s while the ends differ by 60 s: the comparison
disagrees with itself and refutes its own method, exactly as the file-extent
shortcut does with 19 s and 240 s. An earlier draft had the two windows offset by
a constant 15 s at both ends, which made window alignment return a clean, stable
**120.000 s** at both ends — a wrong answer that looks rigorous, and a trap that
punishes a careful reader rather than a careless one. A near-miss route must
disagree with itself. Check both margins after touching either window; the same
holds for the api degraded window, which gives 60 s and 150 s.

Only the orders queues back up; the other four are unaffected, which is what a
database-side failure looks like from the worker.

**Why the database's saturation gauge opens exactly at 09:28:45.** It is the
gauge for the failure the criteria call first, so it must not precede it. An
earlier draft opened it at true 09:28:30, which put a nonzero wait queue 15 s
ahead of the first refused connection — and an answer reporting 97 s of lead time
rather than 87 s would have been reading the file correctly while failing
criteria 8 and 11. It now opens on the anchored instant and closes on the last
tick before `pool_recovered`, so the gauge and the recovery line agree. Its
`in_use` and `idle` partition the declared `size` exactly, on every row of both
pools: a corroborating series whose numbers do not add up is one a careful answer
has to discount.

**How the offset is made exactly recoverable.** For every worker database call the
worker logs a begin at `b` and an end at `e`, and the database logs exactly one
record for that call, stamped at `(b + e) / 2` in its own clock. That is the
ordinary round-trip midpoint estimator, so the pairing is principled rather than a
trick, and it holds for successful executions and for pool failures alike. The
same estimator against the edge's dispatch/respond window gives the worker's
offset as exactly zero. A model that instead uses the cruder `t_db - b` gets
135.023 to 136.500 s with a mean of 135.469 — the same answer to the second, which
is why the criteria allow a one-second tolerance where they are about the
magnitude and not about the method.

**The pairing granularity trap.** The invariant is per database *call*, not per
request. Eight requests made two calls each — a first that hit the exhausted pool
and a retry — so each has two worker windows and two database records. A parser
that keys begins and ends by request id keeps only one of each and crosses the
pairs, which yields nine distinct offsets spanning 133.500 to 135.000 instead of
one. That is a correct estimator applied at the wrong granularity, it is silent,
and criterion 7 names it explicitly so that failing it is fair.

## Ground-truth read-back

`environment/fixtures/GROUND_TRUTH.md` is **generated**, not written by hand. The
read-back stage at the bottom of `build_fixture.sh` shares no state with the
builder: it globs each service's rotation, re-parses every slice from disk with
its own regex, rebuilds the request index from the `req=` fields, recomputes both
offsets, recomputes the monotonicity of each service's concatenated record, and
re-derives the incident timeline. Whatever that stage prints is the file. It also
asserts, per request, that the number of worker begins, worker ends and database
records match — so a shape error in the builder would abort the read-back rather
than produce a plausible-looking wrong file.

The values it produced, all of which appear in `tests/reward.toml`:

- 1,701 / 1,735 / 1,490 lines per service across 4 / 4 / 3 slices; **97** request
  ids present in all three, **0** in only some
- edge-versus-worker offset **0.000 s on 96 of 97** requests, **1.340 s on 1**
- database offset **135.000 s on all 105** request-bearing database records, a
  single distinct value; **2 minutes 15 seconds**; direction **ahead**
- cruder estimator 135.023 … 136.500 s, mean 135.469 s
- file-extent shortcut: first-timestamp difference **19.418 s**, last-timestamp
  difference **240.000 s** — neither is the offset
- **23** requests answered 502, first at **09:30:12.000**; **31**
  pool-exhaustion records, first stamped **09:31:00.000**, corrected
  **09:28:45.000**
- as recorded the database failure looks **48.000 s** later; corrected it is
  **87.000 s** earlier; 48 + 87 = 135
- the impossibility: worker recorded the pool-exhausted response for
  `req-adad6c35` at **09:28:45.900** against the database's own **09:31:00.000**
  — effect before cause by **134.100 s**
- request-by-request: corrected, the database failure precedes the edge's 502 in
  **23 of 23** cases with a margin of **2.440 s**; raw, in **0 of 23**
- **8** requests absorbed by worker retries and still answered 200; **23** worker
  database-call timeouts
- the decoy is `req-8625f445`, `attempt=2`, `requeued=true`,
  `requeue_delay_ms=1340`, answered `202`
- backwards steps in time: **0** in `api`, **1** in `worker` (line 704 at
  `09:17:04.280` following line 703 at `09:17:04.920`, counting from the start of
  the oldest slice), **0** in `db`

Two things the read-back settled rather than confirmed. First, that the moved
claim line produces **exactly one** inversion and not two — the builder inserts it
before a companion request whose own claim falls inside the 1.34 s gap, and the
read-back is what proves the count is one. Second, that no request id is present
in only some of the logs; if any were, "97 shared" would have been a claim about
an intersection rather than about the whole population, and the decoy criterion's
"96 of 97 agree" would have been ambiguous.

## Difficulty design

15 criteria, all weighing 1.0. `tests/reward.toml` carries no weight key anywhere
and rubric E2 forbids adding one, so the reward is a plain mean over the criteria:
12/15 = **0.800**, 11/15 = **0.733**, 10/15 = **0.667**, 9/15 = **0.600**.

Criterion order is Layer 1 → derivation method → Layer 2 inversion → root-cause
call → decoy, so a model that establishes the offset and stops banks the first
block and drops the rest.

The criteria a strong model drops, and why:

1. **The customer-facing count** (criterion 4). 23 requests answered 502, across
   four rotated slices, among 1,701 lines of which 1,410 are health probes. The
   two near misses are in the fixture on purpose: 31 pool-exhaustion records and
   8 absorbed requests. The criterion rejects both.
2. **How the offset was pinned** (criterion 7). A model can get to "about 135
   seconds" by eyeballing and then has no account of it. This criterion demands
   the midpoint estimator *and* the right granularity — see the pairing trap
   above. It also fails any answer that reaches for a timezone explanation, which
   is the single most available wrong story for "one host's timestamps are
   offset", and there is a timezone tool exposed to encourage it.
3. **The order inverts** (criterion 8). The claim that carries the whole task. A
   model that applies the correction to individual timestamps without re-asking
   "which came first" reports a corrected timeline and the original conclusion.
4. **The effect-before-cause observation** (criterion 9). Requires going back to a
   single request and comparing the worker's record of *receiving* a failure
   against the database's record of *emitting* it, and then saying what that
   means. Aggregate reasoning about the two error bursts never produces it, and it
   is the only piece of evidence that makes the raw reading impossible rather than
   merely improbable.
5. **The inversion holds across all 23 requests** (criterion 10). 23 of 23
   corrected, 0 of 23 raw. A model that establishes the inversion for the first
   event of each kind has done enough to write a plausible review and will not do
   this.
6. **What absorbed the silent window** (criterion 11). Needs the 87-second lead
   time *and* the eight retry-absorbed requests that explain why the database was
   failing for 87 seconds without a customer noticing. Without that second part
   the timeline has an unexplained gap, and the natural resolution of an
   unexplained gap is to doubt the correction.
7. **Root cause ruled out** (criterion 13). Models are reluctant to close off a
   hypothesis. The failure mode here is the hedge — "the timeout was too
   aggressive and contributed" — which reads as thorough and is wrong: the timeout
   is the mechanism of visibility, not a cause. The criterion names the hedge.
8. **The decoy is a requeue, not a clock** (criterion 14). The 1.34 s discrepancy
   appears on exactly one of 97 requests, on one line out of 1,735. A model
   computing a mean offset for the edge/worker pair sees a small nonzero number
   and can conclude the worker's clock is off too, which contradicts criterion 2
   and produces a two-bad-clocks review. Excluding it correctly requires noticing
   that skew is uniform by nature and that the offending line carries a requeue
   marker.
9. **The extent shortcut, tried and rejected** (criterion 15). The instruction
   asks which cheaper reads were tried and what each gave, so this is now a
   question the answer was asked. It is still work: the two wrong numbers only
   exist if the comparison was actually made.

Levers used, against the conventions' list: layered defects where the second is
only visible after the first is resolved (1), a criterion that depends on a
quantity the prompt never spells out (2 — the prompt asks for a correction pinned
to the millisecond but says nothing about a per-call pairing or a midpoint
estimator), a required cross-reference across three services and twelve files
where no single file contains the answer (3), a decoy that survives casual
checking (4), and a required direction and ordering that cannot come from one
computation (5 — the sign of the offset and which of the two failures came first).

**No scipy.** Nothing here needs it: the offset is an exact integer-millisecond
difference, the "constant not drift" criterion is a count of distinct values, and
the comparisons are inequalities. Plain Python or pandas is sufficient, and the
criteria are phrased so that no p-value or fitted trend is ever required.

## Claim history

Recorded so a later reviewer does not undo a fix or re-introduce a dead
criterion. Every entry here was a criterion that failed the "graded, not
pass/fail" test in *What this task is scored for*.

- **Two criteria dropped for subsumption and double payment** (commit `3f218a2`).
  One of them, the single backwards step in the worker log, is still described in
  `GROUND_TRUTH.md` and in the oracle answer — it is real, it is worth reporting,
  and it is deliberately not scored. Do not add it back: it is the same finding as
  the decoy criterion approached from the other side.
- **Four criteria were failed identically by all six recorded trials** — the
  customer-facing count, the midpoint estimator, what absorbed the silent window,
  and the extent shortcut — which put every trial in a 0.700–0.767 band and made
  the score a property of the criteria rather than a model result. The judge was
  right on all four; the fault was that no sentence of `instruction.md` asked for
  any of them. The prompt now does, in four added clauses. If a later edit
  shortens the prompt, those four criteria go dead again.
- **Criteria 3 and 7 contradicted each other.** Criterion 3 admitted a spread
  around 135 s; criterion 7 rejected a spread. An answer could satisfy the first
  by construction and fail the second by construction, for the same sentence. They
  now state their boundary explicitly: 3 scores constancy, 7 scores exactness and
  the method that produces it.
- **Criterion 5 was scoring juxtaposition.** Two answers carrying the same two
  uncorrected timestamps scored 0.0 and 0.5 depending on whether the two figures
  appeared in the same sentence. That is judge sensitivity, not a difference in
  what the model established, and noise in the reward is worse than an easy
  criterion. It now accepts both instants stated separately.
- **Criteria 12 and 14 gained explicit rejects** — the wrong pool, and the decoy
  presented as a second bad clock — so that a wrong answer fails for a stated
  reason rather than at the judge's discretion.

## Measured, six live trials + regrade

First live rollout against this fixture, then the same six answers regraded under
the concise claim set. Only `tests/reward.toml` changed between the two columns,
so the comparison is honest.

| | verbose claims | concise claims |
|---|---|---|
| mean | 0.750 | 0.794 |
| sd | 0.060 | **0.095** |
| range | 0.167 | **0.300** |
| live criteria | 7 / 15 | **8 / 15** |
| criteria no trial earns | 1 | **0** |

Scores: glm-5.3 0.833 / 0.833 / 0.900, kimi-k3 0.600 / 0.767 / 0.833. Tool calls
14-39, median 30, against the declared 34. Against the pre-rescope baseline
(mean 0.739, sd 0.024, range 0.067) the spread is roughly four times wider at
about the same mean.

**The lesson the rewrite encodes: the judge scores every subordinate clause as
its own gate.** Three claims lost points to clauses that were never meant to be
requirements. The worst was claim 12's reject, "naming the readonly pool, which
stays healthy throughout, fails" - written to catch an answer naming the wrong
pool, read by the judge as an instruction to discuss the readonly pool. The
correlation was exact: the only answer containing the word `readonly` was the
only one scoring 1.0, and three answers that correctly named primary-pool
exhaustion were docked for omitting an irrelevant healthy pool. Claim 6 lost
points on a rationale clause, claim 11 on a figure whose sibling claim carried a
tolerance and it did not.

So: **one claim, one assertion.** Tolerances inline, rationale in this file,
rejects only where the reject IS the claim. Mean claim length went 62 -> 49 -> 23
words across the three revisions, and the shortest set is also the cleanest
graded.

Claim 7 changed shape rather than wording. It had demanded the round-trip
midpoint estimator and had scored 0 across 17 trials, because every model reaches
135.000 by a different route - one-sided pairing plus the zero-variance timeout
window. It now scores the *result* the prompt actually asks for, a single exact
value rather than a mean, a median or a range, and separates 4 of 6 trials
(135.000 against 134.907 and 134.884, both self-described as medians). A claim
that scores an unreachable method is dead weight; one that scores a reachable
outcome discriminates.

**What is still wrong.** The mean sits at 0.794 against a 0.65 target and seven
claims are earned by every trial. Lowering it is a design change, not a wording
one: either retire free claims for harder ones, or accept the floor. Do not
sharpen claim wording to manufacture failures - that reintroduces exactly the
clause-as-gate defect this section exists to record.

## Tool surface

25 exposed, 8 needed, 6 same-server distractors, 11 off-server distractors —
distractor:needed ratio 17/8 = 2.13. 9 servers, 3 of them carrying needed tools.
`sqlite_delete_records` is not exposed anywhere, and
`desktop-commander_start_process` was removed: an unrestricted shell is not a
near-miss distractor, it is a better tool than the needed set.

Sharpest distractors:

- `time_convert_time` — the sharpest by a distance. A fixed offset between two
  hosts' logs is *exactly* what a timezone bug looks like, and here is a tool for
  timezone arithmetic sitting in the surface. It is the wrong reading twice over:
  every timestamp in all three services is already `Z`, and 135 seconds is not any
  timezone's offset. A model that commits to it burns calls and can land on a
  conclusion that fails criterion 7 outright.
- `time_get_current_time` — near-miss: "now" has nothing to do with a window last
  Thursday, but it is the obvious first reach on a task about time.
- `sqlite_list_tables` / `sqlite_query` — a wrong index. There is a warehouse in
  the image and it has nothing to do with this outage. The temptation is to load
  the logs into it to do the join in SQL, which is a plausible plan that costs
  more than it returns.
- `cli-mcp-server_run_command` — no pipes and `/data` only, so the reflexive
  `grep 'req=' | sort | uniq -c` pipeline is unavailable; a model that commits to
  the shell path has to reimplement it call by call, across twelve files.
- `mcp-code-executor_install_dependencies` — a dead end twice over: pandas is
  already present and the image has no egress.
- `mcp-server-code-runner_run-code` — one-shot with no state, so a parser written
  through it cannot be reused across twelve files.
- `whois_whois_ip` — far-field, but pointed: the logs carry client addresses, so
  there is a visible reason to reach for it and no useful answer at the other end.

The needed set includes `mcp-code-executor_initialize_code_file` and
`_execute_code_file` because `execute_code` is stateless per call and a three-way
join across 4,926 log lines in twelve files is better written once and re-run than
re-pasted.

`target_tool_calls = 34` is a walk against the shipped fixture — discovery 2, one
read per slice 12, a persisted parser written and re-run 8-14, cross-checks on the
decoy, the extents and the per-request inversion 6-10 — and not an aspiration.
Re-measure it from `run_summary.json` after the next live rollout.

## Realism trade

The fixture is synthetic. Real service logs would be messier: multiple formats,
partial lines, sampled traces, unrelated concurrent incidents, requests that
appear in two logs and not the third, and an offset that drifts rather than
holding to the millisecond. The pairing invariant in particular is cleaner than
reality — a real midpoint estimator would scatter by a few milliseconds of
asymmetric network latency rather than returning one distinct value. The trade is
deliberate and it buys full knowability: every criterion quotes a value read back
out of the artefact, with no `[DERIVE]`.

The criterion structure would survive a swap to real telemetry, because each one
describes a *pattern* rather than a particular outage: one host's clock offset by
a constant recoverable only by cross-service correlation on a shared identifier,
a causal order that inverts under the correction and reassigns the root cause, a
per-request confirmation that the inversion is not an artefact of picking the
first event, and an application-level retry that mimics skew on a single request.
Re-pointing the fixture would mean re-running the read-back stage, loosening the
"single distinct value" criterion to a tolerance, and re-writing the numbers; the
phase chain and the weighting would not change.

## Cross-task overlap

`/data/logs/` is a new path and the task injects nothing into `turing.db` at all,
so there is no collision with the eight baked tables, with
`journal-balance-forensics`'s `gl_period_close`, with `migration-order-drift`'s
`svc_*` tables, or with the other v2 fixtures. The tool allowlist overlaps with
the other filesystem/code-executor tasks in the suite, which is intended — the
allowlist is not a differentiator. This is the only task in the pair that exposes
the `time` server, and the only one that does not need `sqlite`.

## Not verified

- **No `docker build` of `environment/Dockerfile` on a clean host.** The build
  assertions were dry-run against the emitted fixture on the authoring host and
  all pass, but the image has not been built against a registry pull of
  `us-central1-docker.pkg.dev/turing-delivery-rl-gym/daytona/turing-mcpatlas:0.0.3`.
- **No live rollout against this version of the fixture or the criteria.** The
  recorded trials under `jobs/` were produced against the 954-line single-file
  corpus and the previous criteria text, so none of them is evidence about this
  version. Oracle and nop must be re-gated and both models re-run live — a regrade
  of a recorded answer cannot test a changed fixture.
- **`target_tool_calls = 34` is a walk, not a measurement.** It replaces a figure
  (56) that measurement had already contradicted; correct it from
  `run_summary.json` once live runs exist.
- **The projected score band is a projection.** The variance argument in *What
  this task is scored for* rests on which criteria are reachable, not on observed
  scores. Nothing here has been measured against the changed prompt.
- **No cross-judge comparison exists.** Every score in this suite came from
  `openrouter/openai/gpt-5.6-luna`, which rubric v1.1 mandates, so the judge
  conforms — but no second judge has graded this task and scores are only
  comparable within one judge.
- **No Nemotron and no GLM-5.2 rollout.** The difficulty floor is evidenced by
  kimi-k3 and glm-5.3 only, and only against the superseded fixture.
