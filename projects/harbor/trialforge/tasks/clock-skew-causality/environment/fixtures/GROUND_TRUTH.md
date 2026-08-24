# GROUND_TRUTH.md — clock-skew-causality

Everything below was read **back out of the built artefacts**: the three log
files were re-parsed from `logs/` on disk by the read-back stage of
`build_fixture.sh`, which uses its own parser and shares no state with the
builder. `bash build_fixture.sh` regenerates this file. All times are printed
as recorded, i.e. in each host's OWN clock, unless a line says *corrected*.

## Shape

Each service's record is ROTATED. `<svc>.log` is the newest slice and
`<svc>.log.N` the oldest; read in the order below they are one continuous
file with no gap and no overlap. Line numbers in this document count from
the start of the oldest slice. A count taken from any single slice is a
count of that slice, not of the service.

- `api` rotation, oldest first: `api.log.3` (426), `api.log.2` (426), `api.log.1` (426), `api.log` (423)
- `worker` rotation, oldest first: `worker.log.3` (434), `worker.log.2` (434), `worker.log.1` (434), `worker.log` (433)
- `db` rotation, oldest first: `db.log.3` (373), `db.log.2` (373), `db.log.1` (373), `db.log` (371)

- `api` in total: **1701** lines, **97** distinct request ids, **1410** lines with no request id
- `worker` in total: **1735** lines, **97** distinct request ids, **1428** lines with no request id
- `db` in total: **1490** lines, **97** distinct request ids, **1385** lines with no request id
- request ids present in **all three** logs: **97**
- request ids present in only some: **0**
- hosts, one per log: api-7c, pgdb-01, worker-3a
- every timestamp is UTC (`Z`); no line in any log names a time source, a
  timezone offset or a clock.
- levels: api ERROR 23, INFO 1665, WARN 13 | worker ERROR 23, INFO 1704, WARN 8 | db ERROR 31, INFO 1437, WARN 22

## Where each file steps backwards in time

- `api`: **0** line(s) stamped earlier than the line above
- `worker`: **1** line(s) stamped earlier than the line above
  - line 704 at `09:17:04.280` follows line 703 at `09:17:04.920`
  - the line above it is the out-of-position one: `2024-11-14T09:17:04.920Z INFO  worker host=worker-3a req=req-8625f445 stage=claimed attempt=2 queue=orders.work requeued=true requeue_delay_ms=1340`
- `db`: **0** line(s) stamped earlier than the line above

## Estimator 1 — edge against worker, paired on request id

For each request the edge logs `stage=dispatched` at d and `stage=responded`
at p; the worker logs `stage=claimed` at c. The round-trip midpoint estimate
of the worker's offset from the edge is c - (d + p) / 2.

- offset **0.000 s** on **96** of 97 requests
- offset **1.340 s** on **1** of 97 requests

- the single request that does not agree is **`req-8625f445`**, off by **+1.340 s**. Its claim line is:
  ```
  2024-11-14T09:17:04.920Z INFO  worker host=worker-3a req=req-8625f445 stage=claimed attempt=2 queue=orders.work requeued=true requeue_delay_ms=1340
  ```
  It carries `attempt=2`, `requeued=true` and `requeue_delay_ms=1340`, and the edge answered it `status=202` before the worker ever claimed it. This is an application-level requeue,
  not a clock difference: a clock difference would show on every request,
  and the other 96 requests agree to the millisecond.
- **conclusion: the edge and worker clocks agree exactly.**

## Estimator 2 — worker against database, paired on request id

For each worker database call the worker logs `stage=db_call_begin` at b and
`stage=db_call_end`/`db_call_timeout` at e; the database logs exactly one
record for that call. The same midpoint estimator gives the database host's
offset as t_db - (b + e) / 2.

- database records carrying a request id: **105**
- offset **135.000 s** on **105** of 105 of them
- distinct values: **1** — the offset is a CONSTANT, not drift and
  not jitter: one subtraction corrects the whole file.
- direction: the database host is **AHEAD**. Its timestamps must be reduced
  by 135.000 s to compare with the other two.
- 135.000 s stated as minutes and seconds: **2 minutes 15 seconds**
- for comparison, the cruder estimator t_db - b gives 135.023 to 136.500 s, mean 135.469 s — the same answer to the second.

### What the cheap shortcut gives instead

Comparing the files' own extents rather than pairing on request id does NOT
recover the offset, because the database's background chatter covers a wider
true-time span than the other two logs:

| log | first timestamp | last timestamp |
|---|---|---|
| `api` | `2024-11-14T09:00:00.582Z` | `09:39:20.000` |
| `worker` | `2024-11-14T09:00:00.692Z` | `09:39:40.000` |
| `db` | `2024-11-14T09:00:20.000Z` | `09:43:20.000` |

- first-timestamp difference db - api: **19.418 s**
- last-timestamp difference db - api: **240.000 s**
- neither is the offset (135.000 s).

## The causal order, as recorded and corrected

- `status=502` responses in `api.log`: **23**
- `msg=pool_exhausted` records in `db.log`: **31**
- first 502, edge clock: **09:30:12.000** (`req-0269f794`)
- first pool exhaustion, AS RECORDED: **09:31:00.000** (`req-adad6c35`)
- first pool exhaustion, CORRECTED: **09:28:45.000**

- as recorded, the database failure looks **48.000 s LATER** than the first 502
- corrected, it is **87.000 s EARLIER**
- the two differ by exactly the offset: 48.000 + 87.000 = 135.000

Corrected sequence of the incident:

1. `09:28:45.000` database connection pool exhausted (`req-adad6c35`, corrected)
2. `09:28:45.900` worker records receiving a pool-exhausted response (`req-adad6c35`) and retries
3. `09:30:11.060` first worker database-call timeout (`req-0269f794`)
4. `09:30:12.000` first customer-visible 502 at the edge

The step that makes the raw reading impossible rather than merely odd:

- worker recorded the pool-exhausted response for `req-adad6c35` at **09:28:45.900**
- the database's own record of that same request's failure is stamped **09:31:00.000**
- as recorded the effect precedes its cause by **134.100 s**; corrected, the cause precedes the effect by **0.900 s**

- worker retries absorbed the first burst: **8** requests took a pool-exhausted response, retried and were answered 200 by the edge
- worker database-call timeouts: **23**
- lead time: the database was already failing **87.000 s** before the first customer-visible error

## Does the inversion hold request by request?

- of the **23** requests answered 502, the corrected database
  failure for the SAME request precedes the edge's 502 in **23** cases and
  follows it in **0**
- margin range: 2.440 to 2.440 s
- with the raw timestamps the same test puts the database failure first in
  **0** of 23 cases — the inversion is total, not marginal

## Lines that look like evidence and are not

- `stage=healthcheck` lines in `api.log`: 1410, of which **13** report `status=degraded`. They carry no request id, so they
  cannot be paired across services and contribute nothing to the offset.
- `op=pool_stats` lines in `db.log`: **518**; `op=checkpoint` 87; `op=autovacuum` 132. Also unpairable.
- `op=heartbeat` lines in `worker.log`: 1428.

## Numbers that appear in no claim

Individual request ids other than the requeued one, routes, client addresses,
statement names, row counts, queue depths, checkpoint buffer counts and
autovacuum tuple counts are seeded filler. Only the values above are asserted.
