#!/bin/bash
# Emits logs/<svc>.log[.1-.3] for api, worker and db, then regenerates
# GROUND_TRUTH.md from them. Deterministic. What it encodes and why: NOTES.md.

set -euo pipefail
cd "$(dirname "$0")"

rm -rf logs
mkdir -p logs

python3 - <<'BUILD'
import random

rng = random.Random(20241114)

DAY = "2024-11-14"
SKEW_MS = 135_000                     # db host runs this far AHEAD of the rest
API_HOST, WRK_HOST, DB_HOST = "api-7c", "worker-3a", "pgdb-01"

def ts(ms):
    """ms since 2024-11-14T00:00:00Z -> ISO-8601 with milliseconds, Z."""
    s, msec = divmod(ms, 1000)
    m, sec = divmod(s, 60)
    h, mi = divmod(m, 60)
    return f"{DAY}T{h:02d}:{mi:02d}:{sec:02d}.{msec:03d}Z"

def hm(h, m, s=0, ms=0):
    return ((h * 60 + m) * 60 + s) * 1000 + ms

REQ_SEEN = set()
def new_req():
    while True:
        r = "req-" + "".join(rng.choice("0123456789abcdef") for _ in range(8))
        if r not in REQ_SEEN:
            REQ_SEEN.add(r)
            return r

ROUTES = ["POST:/v1/checkout", "POST:/v1/cart/items", "GET:/v1/cart",
          "POST:/v1/orders", "GET:/v1/orders", "POST:/v1/payment/authorize"]
STMTS = ["orders_insert", "cart_select", "cart_upsert", "order_lines_insert",
         "payment_intent_insert", "customer_select"]
CLIENTS = ["203.0.113.%d" % i for i in (17, 44, 91, 126, 203, 8, 55, 240)]

api_lines, wrk_lines, db_lines = [], [], []          # (ms_in_own_clock, text)

def api(t, level, req, **kv):
    body = " ".join(f"{k}={v}" for k, v in kv.items())
    api_lines.append((t, f"{ts(t)} {level:<5} api    host={API_HOST}"
                         + (f" req={req}" if req else "") + f" {body}"))

def wrk(t, level, req, **kv):
    body = " ".join(f"{k}={v}" for k, v in kv.items())
    wrk_lines.append((t, f"{ts(t)} {level:<5} worker host={WRK_HOST}"
                         + (f" req={req}" if req else "") + f" {body}"))

def db(t_wall, level, req, **kv):
    """t_wall is TRUE time; the line is stamped in the db host's own clock."""
    t = t_wall + SKEW_MS
    body = " ".join(f"{k}={v}" for k, v in kv.items())
    db_lines.append((t, f"{ts(t)} {level:<5} db     host={DB_HOST}"
                        + (f" req={req}" if req else "") + f" {body}"))

# request shapes. INVARIANT: one db record per worker window (b, e), stamped at
# (b + e) / 2 + SKEW_MS; the worker's claim at the edge's midpoint, offset 0.

def emit_healthy(req, t_recv, dur, b_off, span, route, stmt, client,
                 status=200, claim_shift=0, claim_extra=None):
    t_disp = t_recv + 40
    t_resp = t_disp + dur                       # dur even -> integral midpoint
    claim = (t_disp + t_resp) // 2 + claim_shift
    b = claim + b_off
    e = b + span                                # span even
    mid = (b + e) // 2
    rows = rng.randint(1, 40)
    api(t_recv, "INFO", req, stage="received", route=route, client=client)
    api(t_disp, "INFO", req, stage="dispatched", queue="orders.work")
    api(t_resp, "INFO", req, stage="responded", status=status, duration_ms=dur)
    kv = {"stage": "claimed", "attempt": 1, "queue": "orders.work"}
    if claim_extra:
        kv.update(claim_extra)
    wrk(claim, "INFO", req, **kv)
    wrk(b, "INFO", req, stage="db_call_begin", backend="primary", stmt=stmt)
    wrk(e, "INFO", req, stage="db_call_end", rows=rows, elapsed_ms=span)
    db(mid, "INFO", req, op="execute", stmt=stmt, rows=rows,
       elapsed_ms=span - rng.randint(8, 30))
    return claim

def emit_retried(req, t_recv, dur, b1, span1, b2_gap, span2, route, stmt, client, waiting):
    """Pool failure absorbed by a worker retry: the edge still returns 200."""
    t_disp = t_recv + 40
    t_resp = t_disp + dur
    claim = (t_disp + t_resp) // 2
    e1 = b1 + span1
    mid1 = (b1 + e1) // 2
    b2 = e1 + b2_gap
    e2 = b2 + span2
    mid2 = (b2 + e2) // 2
    rows = rng.randint(1, 40)
    api(t_recv, "INFO", req, stage="received", route=route, client=client)
    api(t_disp, "INFO", req, stage="dispatched", queue="orders.work")
    api(t_resp, "INFO", req, stage="responded", status=200, duration_ms=dur)
    wrk(claim, "INFO", req, stage="claimed", attempt=1, queue="orders.work")
    wrk(b1, "INFO", req, stage="db_call_begin", backend="primary", stmt=stmt)
    wrk(e1, "WARN", req, stage="db_call_end", result="pool_exhausted",
        elapsed_ms=span1)
    wrk(b2, "INFO", req, stage="db_call_begin", backend="primary", stmt=stmt,
        attempt=2)
    wrk(e2, "INFO", req, stage="db_call_end", rows=rows, elapsed_ms=span2,
        attempt=2)
    db(mid1, "ERROR", req, op="acquire_connection", msg="pool_exhausted",
       pool="primary", in_use=20, waiting=waiting)
    db(mid2, "INFO", req, op="execute", stmt=stmt, rows=rows,
       elapsed_ms=span2 - rng.randint(8, 30))
    return mid1

def emit_failed(req, t_resp, route, stmt, client, waiting):
    """Pool failure the retry budget could not absorb: the edge returns 502."""
    dur = 8000
    claim = t_resp - dur // 2
    t_disp = claim - dur // 2
    t_recv = t_disp - 40
    b = claim + 60
    e = b + 3000
    mid = (b + e) // 2
    api(t_recv, "INFO", req, stage="received", route=route, client=client)
    api(t_disp, "INFO", req, stage="dispatched", queue="orders.work")
    api(t_resp, "ERROR", req, stage="responded", status=502, duration_ms=dur,
        error="upstream_timeout")
    wrk(claim, "INFO", req, stage="claimed", attempt=1, queue="orders.work")
    wrk(b, "INFO", req, stage="db_call_begin", backend="primary", stmt=stmt)
    wrk(e, "ERROR", req, stage="db_call_timeout", waited_ms=3000, backend="primary")
    db(mid, "ERROR", req, op="acquire_connection", msg="pool_exhausted",
       pool="primary", in_use=20, waiting=waiting)
    return mid

# ── 64 ordinary requests on a 35 s grid across the whole window ─────────────
for k in range(64):
    t_recv = hm(9, 0, 0) + k * 35_000 + rng.randrange(0, 4000, 2)
    emit_healthy(new_req(), t_recv,
                 dur=rng.randrange(120, 900, 2),
                 b_off=rng.randint(12, 45),
                 span=rng.randrange(40, 320, 2),
                 route=rng.choice(ROUTES), stmt=rng.choice(STMTS),
                 client=rng.choice(CLIENTS))

# ── the requeued request (the decoy) and its companion ─────────────────────
# The companion is what makes the backwards step count exactly one, not zero.
COMPANION_REQ = new_req()
emit_healthy(COMPANION_REQ, hm(9, 17, 3, 700), dur=1080, b_off=40, span=240,
             route="GET:/v1/cart", stmt="cart_select", client="203.0.113.91")

DECOY_REQ = new_req()
DECOY_CLAIM = emit_healthy(
    DECOY_REQ, hm(9, 17, 3, 100), dur=880, b_off=60, span=240,
    route="POST:/v1/cart/items", stmt="cart_upsert", client="203.0.113.126",
    status=202, claim_shift=1340,
    claim_extra={"attempt": 2, "requeued": "true", "requeue_delay_ms": 1340})

# ── phase A: 8 pool failures absorbed by worker retries, edge still 200 ────
# A1 anchors the first db record at TRUE 09:28:45.000 = recorded 09:31:00.000.
PHASE_A = [
    # (t_recv,                b1,                    span1, gap, span2, waiting)
    (hm(9, 28, 41, 500), hm(9, 28, 44, 100), 1800, 250, 330, 3),
    (hm(9, 28, 53, 200), hm(9, 28, 55, 800), 1600, 220, 290, 4),
    (hm(9, 29,  6, 100), hm(9, 29,  8, 700), 1900, 260, 350, 6),
    (hm(9, 29, 18, 400), hm(9, 29, 21,   0), 1700, 240, 310, 7),
    (hm(9, 29, 29, 900), hm(9, 29, 32, 500), 2000, 230, 300, 9),
    (hm(9, 29, 39, 200), hm(9, 29, 41, 800), 1800, 250, 320, 11),
    (hm(9, 29, 49, 600), hm(9, 29, 52, 200), 2100, 270, 360, 13),
    (hm(9, 29, 58, 100), hm(9, 30,  0, 700), 1900, 240, 330, 15),
]
PHASE_A_REQS = []
for t_recv, b1, span1, gap, span2, waiting in PHASE_A:
    r = new_req()
    PHASE_A_REQS.append(r)
    claim = b1 - 60
    dur = 2 * (claim - (t_recv + 40))
    emit_retried(r, t_recv, dur, b1, span1, gap, span2,
                 route=rng.choice(ROUTES), stmt=rng.choice(STMTS),
                 client=rng.choice(CLIENTS), waiting=waiting)

# ── phase B: 23 requests the retry budget could not save -> 502 ───────────
# B1 is anchored so the edge's first 502 is stamped 09:30:12.000.
PHASE_B_REQS = []
for k in range(23):
    t_resp = hm(9, 30, 12, 0) + k * 4_700 + (rng.randrange(0, 600, 2) if k else 0)
    r = new_req()
    PHASE_B_REQS.append(r)
    emit_failed(r, t_resp, route=rng.choice(ROUTES), stmt=rng.choice(STMTS),
                client=rng.choice(CLIENTS), waiting=16 + k)

# ═════════════════════════════════════════════════════════════════════════════
# background noise — no req= field, so none of it pairs across services
# ═════════════════════════════════════════════════════════════════════════════

# EVERY SERIES IS PINNED AT BOTH ENDS and every step divides its span exactly:
# criterion 15's 19.418 s / 240.000 s are measured off those ticks. See NOTES.md.

# ── api: upstream health probes, 6 upstreams every 10 s ─────────────────────
# Last tick IS api's last timestamp. Only the orders upstream degrades.
API_UPSTREAMS = ["worker.orders", "cache.session", "authz.tokens",
                 "search.catalog", "media.assets", "ledger.postings"]
for t in range(hm(9, 0, 20), hm(9, 39, 20) + 1, 10_000):
    for up in API_UPSTREAMS:
        degraded = up == "worker.orders" and hm(9, 30, 0) <= t <= hm(9, 32, 0)
        api(t, "WARN" if degraded else "INFO", None, stage="healthcheck",
            upstream=up, status="degraded" if degraded else "ok",
            p99_ms=rng.randint(1800, 4200) if degraded else rng.randint(38, 120))

# ── worker: per-queue heartbeats, 6 queues every 10 s ───────────────────────
# Hot 09:29:10-09:33:30, opening 25 s AFTER the corrected pool failure so the
# surge reads as a consequence. Margins must stay UNEQUAL — see NOTES.md.
WRK_QUEUES = ["orders.work", "orders.retry", "payments.work",
              "payments.retry", "notify.work", "reindex.work"]
for t in range(hm(9, 0, 10), hm(9, 39, 40) + 1, 10_000):
    hot = hm(9, 29, 10) <= t <= hm(9, 33, 30)
    for q in WRK_QUEUES:
        busy = hot and q.startswith("orders")
        wrk(t, "INFO", None, op="heartbeat", queue=q,
            queue_depth=rng.randint(180, 640) if busy else rng.randint(0, 9),
            inflight=rng.randint(28, 32) if busy else rng.randint(1, 6))

# ── db: five maintenance series, all spanning true 08:58:05 -> 09:41:05 ─────
# 2,580 s, which divides exactly by 5 s, 10 s, 20 s, 30 s and 60 s.
BG_FIRST, BG_LAST = hm(8, 58, 5), hm(9, 41, 5)

def db_hot(t_wall):
    # Opens ON the anchored first pool exhaustion, never before: a wait queue
    # ahead of it would make 97 s of lead time a correct read. See NOTES.md.
    return hm(9, 28, 45) <= t_wall <= hm(9, 32, 20)

for t_wall in range(BG_FIRST, BG_LAST + 1, 5_000):            # WAL writer
    db(t_wall, "INFO", None, op="wal_write",
       segment="0000000100000A%02X" % rng.randint(0, 255),
       bytes_written=rng.randint(8_192, 1_048_576),
       sync_ms=rng.randint(1, 40))

# Two pools, one host. Only `primary` saturates; `readonly` stays healthy.
for t_wall in range(BG_FIRST, BG_LAST + 1, 10_000):           # pool gauges
    for pool, cap in (("primary", 20), ("readonly", 12)):
        hot = db_hot(t_wall) and pool == "primary"
        # in_use + idle == cap, always. The two numbers partition the pool.
        in_use = cap if hot else rng.randint(3, cap - 6)
        db(t_wall, "WARN" if hot else "INFO", None, op="pool_stats", pool=pool,
           size=cap, in_use=in_use, idle=cap - in_use,
           waiting=rng.randint(9, 24) if hot else 0)

for t_wall in range(BG_FIRST, BG_LAST + 1, 30_000):           # checkpoints
    db(t_wall, "INFO", None, op="checkpoint",
       buffers_written=rng.randint(400, 5200), sync_ms=rng.randint(4, 90))

for t_wall in range(BG_FIRST, BG_LAST + 1, 60_000):           # autovacuum
    for tbl in ("orders", "cart_items", "payment_intents"):
        db(t_wall, "INFO", None, op="autovacuum", table=tbl,
           tuples_removed=rng.randint(0, 9000))

for t_wall in range(BG_FIRST, BG_LAST + 1, 20_000):           # bgwriter
    db(t_wall, "INFO", None, op="bgwriter",
       buffers_clean=rng.randint(0, 3400),
       maxwritten_clean=rng.randint(0, 12))

db(hm(9, 32, 15), "INFO", None, op="pool_recovered", pool="primary",
   available=20, waited_total_ms=210_400)

# ═════════════════════════════════════════════════════════════════════════════
# emit
# ═════════════════════════════════════════════════════════════════════════════
api_lines.sort(key=lambda x: x[0])
db_lines.sort(key=lambda x: x[0])
wrk_lines.sort(key=lambda x: x[0])

# Move the requeued claim line to where its original enqueue point would sort.
# Exactly one backwards step results.
decoy_claim_idx = next(i for i, (t, txt) in enumerate(wrk_lines)
                       if t == DECOY_CLAIM and "stage=claimed" in txt)
decoy_claim = wrk_lines.pop(decoy_claim_idx)
target = DECOY_CLAIM - 1340
insert_at = next(i for i, (t, _) in enumerate(wrk_lines) if t > target)
wrk_lines.insert(insert_at, decoy_claim)

# Rotate: `<svc>.log` newest, `<svc>.log.N` oldest. Each slice reads whole under
# tool_output_cap; a service's rotation does not. See NOTES.md.
ROTATION = {"api": 4, "worker": 4, "db": 4}   # keeps every slice well under the cap
for name, lines in (("api", api_lines), ("worker", wrk_lines), ("db", db_lines)):
    n = ROTATION[name]
    size = -(-len(lines) // n)          # ceil: newest slice is the short one
    chunks = [lines[i:i + size] for i in range(0, len(lines), size)]
    assert len(chunks) == n, (name, len(chunks), n)
    for k, chunk in enumerate(chunks):          # chunks[0] is the OLDEST
        suffix = "" if k == n - 1 else f".{n - 1 - k}"
        path = f"logs/{name}.log{suffix}"
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(t for _, t in chunk) + "\n")
        print(f"wrote {path}  {len(chunk)} lines")
BUILD

# ═════════════════════════════════════════════════════════════════════════════
# READ-BACK — own parser, no shared state with the builder above.
# GROUND_TRUTH.md is whatever this stage prints.
# ═════════════════════════════════════════════════════════════════════════════
python3 - <<'READBACK'
import glob
import re
from collections import Counter, defaultdict

PAT = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T(?P<h>\d{2}):(?P<mi>\d{2}):(?P<s>\d{2})\.(?P<ms>\d{3})Z)"
    r"\s+(?P<level>\w+)\s+(?P<svc>\w+)\s+(?P<rest>.*)$")

def slices(svc):
    """A service's rotation, oldest first: <svc>.log.N ... <svc>.log.1, <svc>.log."""
    rot = sorted(glob.glob(f"logs/{svc}.log.*"),
                 key=lambda q: -int(q.rsplit(".", 1)[1]))
    return rot + [f"logs/{svc}.log"]

def parse(svc):
    rows = []
    lineno = 0
    for path in slices(svc):
      for raw in open(path, encoding="utf-8"):
        lineno += 1
        raw = raw.rstrip("\n")
        m = PAT.match(raw)
        assert m, (path, lineno, raw)
        t = (((int(m["h"]) * 60 + int(m["mi"])) * 60 + int(m["s"])) * 1000
             + int(m["ms"]))
        kv = dict(p.split("=", 1) for p in m["rest"].split() if "=" in p)
        rows.append({"lineno": lineno, "ts": m["ts"], "ms": t, "file": path,
                     "level": m["level"], "svc": m["svc"], "kv": kv, "raw": raw})
    return rows

api = parse("api")
wrk = parse("worker")
dbl = parse("db")

def fmt(ms):
    s, msec = divmod(ms, 1000)
    m, sec = divmod(s, 60)
    h, mi = divmod(m, 60)
    return f"{h:02d}:{mi:02d}:{sec:02d}.{msec:03d}"

def secs(ms):
    return f"{ms / 1000:.3f}"

out = []
w = out.append
w("# GROUND_TRUTH.md — clock-skew-causality")
w("")
w("Everything below was read **back out of the built artefacts**: the three log")
w("files were re-parsed from `logs/` on disk by the read-back stage of")
w("`build_fixture.sh`, which uses its own parser and shares no state with the")
w("builder. `bash build_fixture.sh` regenerates this file. All times are printed")
w("as recorded, i.e. in each host's OWN clock, unless a line says *corrected*.")
w("")

# ── shape ──────────────────────────────────────────────────────────────────
w("## Shape")
w("")
w("Each service's record is ROTATED. `<svc>.log` is the newest slice and")
w("`<svc>.log.N` the oldest; read in the order below they are one continuous")
w("file with no gap and no overlap. Line numbers in this document count from")
w("the start of the oldest slice. A count taken from any single slice is a")
w("count of that slice, not of the service.")
w("")
for svc in ("api", "worker", "db"):
    parts = ", ".join(f"`{q[5:]}` ({sum(1 for _ in open(q, encoding='utf-8'))})"
                      for q in slices(svc))
    w(f"- `{svc}` rotation, oldest first: {parts}")
w("")
for name, rows in (("api", api), ("worker", wrk), ("db", dbl)):
    reqs = {r["kv"]["req"] for r in rows if "req" in r["kv"]}
    w(f"- `{name}` in total: **{len(rows)}** lines, **{len(reqs)}** distinct request ids, "
      f"**{sum(1 for r in rows if 'req' not in r['kv'])}** lines with no request id")
areq = {r["kv"]["req"] for r in api if "req" in r["kv"]}
wreq = {r["kv"]["req"] for r in wrk if "req" in r["kv"]}
dreq = {r["kv"]["req"] for r in dbl if "req" in r["kv"]}
common = areq & wreq & dreq
w(f"- request ids present in **all three** logs: **{len(common)}**")
w(f"- request ids present in only some: **{len((areq | wreq | dreq) - common)}**")
w("- hosts, one per log: "
  + ", ".join(sorted({r['kv']['host'] for r in api + wrk + dbl})))
w("- every timestamp is UTC (`Z`); no line in any log names a time source, a")
w("  timezone offset or a clock.")
w(f"- levels: api " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r['level'] for r in api).items()))
  + " | worker " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r['level'] for r in wrk).items()))
  + " | db " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r['level'] for r in dbl).items())))
w("")

# ── monotonicity ───────────────────────────────────────────────────────────
w("## Where each file steps backwards in time")
w("")
for name, rows in (("api", api), ("worker", wrk), ("db", dbl)):
    inv = [r for prev, r in zip(rows, rows[1:]) if r["ms"] < prev["ms"]]
    w(f"- `{name}`: **{len(inv)}** line(s) stamped earlier than the line above")
    for r in inv:
        prev = rows[r["lineno"] - 2]
        w(f"  - line {r['lineno']} at `{fmt(r['ms'])}` follows line "
          f"{prev['lineno']} at `{fmt(prev['ms'])}`")
        w(f"  - the line above it is the out-of-position one: `{prev['raw']}`")
w("")

# ── api <-> worker offset ─────────────────────────────────────────────────
w("## Estimator 1 — edge against worker, paired on request id")
w("")
w("For each request the edge logs `stage=dispatched` at d and `stage=responded`")
w("at p; the worker logs `stage=claimed` at c. The round-trip midpoint estimate")
w("of the worker's offset from the edge is c - (d + p) / 2.")
w("")
disp = {r["kv"]["req"]: r["ms"] for r in api if r["kv"].get("stage") == "dispatched"}
resp = {r["kv"]["req"]: r["ms"] for r in api if r["kv"].get("stage") == "responded"}
claim = {}
claim_row = {}
for r in wrk:
    if r["kv"].get("stage") == "claimed":
        claim[r["kv"]["req"]] = r["ms"]
        claim_row[r["kv"]["req"]] = r
aw = {}
for q in sorted(common):
    aw[q] = claim[q] - (disp[q] + resp[q]) // 2
hist = Counter(aw.values())
for v, c in sorted(hist.items()):
    w(f"- offset **{secs(v)} s** on **{c}** of {len(aw)} requests")
odd = sorted(q for q, v in aw.items() if v != 0)
w("")
for q in odd:
    r = claim_row[q]
    w(f"- the single request that does not agree is **`{q}`**, off by "
      f"**+{secs(aw[q])} s**. Its claim line is:")
    w("  ```")
    w("  " + r["raw"])
    w("  ```")
    w(f"  It carries `attempt=2`, `requeued=true` and `requeue_delay_ms="
      f"{r['kv'].get('requeue_delay_ms')}`, and the edge answered it "
      f"`status={resp and [x['kv']['status'] for x in api if x['kv'].get('req') == q and x['kv'].get('stage') == 'responded'][0]}` "
      "before the worker ever claimed it. This is an application-level requeue,")
    w("  not a clock difference: a clock difference would show on every request,")
    w(f"  and the other {len(aw) - len(odd)} requests agree to the millisecond.")
w("- **conclusion: the edge and worker clocks agree exactly.**")
w("")

# ── worker <-> db offset ─────────────────────────────────────────────────
w("## Estimator 2 — worker against database, paired on request id")
w("")
w("For each worker database call the worker logs `stage=db_call_begin` at b and")
w("`stage=db_call_end`/`db_call_timeout` at e; the database logs exactly one")
w("record for that call. The same midpoint estimator gives the database host's")
w("offset as t_db - (b + e) / 2.")
w("")
begins = defaultdict(list)
ends = defaultdict(list)
for r in wrk:
    st = r["kv"].get("stage")
    if st == "db_call_begin":
        begins[r["kv"]["req"]].append(r["ms"])
    elif st in ("db_call_end", "db_call_timeout"):
        ends[r["kv"]["req"]].append(r["ms"])
dbreq = defaultdict(list)
for r in dbl:
    if "req" in r["kv"]:
        dbreq[r["kv"]["req"]].append(r)

offsets = []
paired = 0
for q in sorted(dbreq):
    bs, es = sorted(begins[q]), sorted(ends[q])
    rs = sorted(dbreq[q], key=lambda r: r["ms"])
    assert len(bs) == len(es) == len(rs), (q, len(bs), len(es), len(rs))
    for b, e, r in zip(bs, es, rs):
        offsets.append(r["ms"] - (b + e) // 2)
        paired += 1
oh = Counter(offsets)
w(f"- database records carrying a request id: **{paired}**")
for v, c in sorted(oh.items()):
    w(f"- offset **{secs(v)} s** on **{c}** of {paired} of them")
w(f"- distinct values: **{len(oh)}** — the offset is a CONSTANT, not drift and")
w("  not jitter: one subtraction corrects the whole file.")
w(f"- direction: the database host is **AHEAD**. Its timestamps must be reduced")
w(f"  by {secs(max(oh))} s to compare with the other two.")
w(f"- {secs(max(oh))} s stated as minutes and seconds: "
  f"**{max(oh) // 60000} minutes {max(oh) % 60000 / 1000:.0f} seconds**")
naive = []
for q in sorted(dbreq):
    bs = sorted(begins[q]); rs = sorted(dbreq[q], key=lambda r: r["ms"])
    for b, r in zip(bs, rs):
        naive.append(r["ms"] - b)
w(f"- for comparison, the cruder estimator t_db - b gives "
  f"{secs(min(naive))} to {secs(max(naive))} s, mean {sum(naive)/len(naive)/1000:.3f} s "
  "— the same answer to the second.")
OFF = max(oh)
w("")
w("### What the cheap shortcut gives instead")
w("")
w("Comparing the files' own extents rather than pairing on request id does NOT")
w("recover the offset, because the database's background chatter covers a wider")
w("true-time span than the other two logs:")
w("")
w("| log | first timestamp | last timestamp |")
w("|---|---|---|")
for name, rows in (("api", api), ("worker", wrk), ("db", dbl)):
    w(f"| `{name}` | `{rows[0]['ts']}` | `{max(r['ms'] for r in rows) and fmt(max(r['ms'] for r in rows))}` |")
w("")
a0, d0 = min(r["ms"] for r in api), min(r["ms"] for r in dbl)
a1, d1 = max(r["ms"] for r in api), max(r["ms"] for r in dbl)
w(f"- first-timestamp difference db - api: **{secs(d0 - a0)} s**")
w(f"- last-timestamp difference db - api: **{secs(d1 - a1)} s**")
w(f"- neither is the offset ({secs(OFF)} s).")
w("")

# ── the inversion ────────────────────────────────────────────────────────
w("## The causal order, as recorded and corrected")
w("")
five02 = [r for r in api if r["kv"].get("status") == "502"]
pool = [r for r in dbl if r["kv"].get("msg") == "pool_exhausted"]
first502 = min(five02, key=lambda r: r["ms"])
firstpool = min(pool, key=lambda r: r["ms"])
w(f"- `status=502` responses in `api.log`: **{len(five02)}**")
w(f"- `msg=pool_exhausted` records in `db.log`: **{len(pool)}**")
w(f"- first 502, edge clock: **{fmt(first502['ms'])}** (`{first502['kv']['req']}`)")
w(f"- first pool exhaustion, AS RECORDED: **{fmt(firstpool['ms'])}** "
  f"(`{firstpool['kv']['req']}`)")
w(f"- first pool exhaustion, CORRECTED: **{fmt(firstpool['ms'] - OFF)}**")
w("")
w(f"- as recorded, the database failure looks **{secs(firstpool['ms'] - first502['ms'])} s "
  f"LATER** than the first 502")
w(f"- corrected, it is **{secs(first502['ms'] - (firstpool['ms'] - OFF))} s EARLIER**")
w(f"- the two differ by exactly the offset: {secs(firstpool['ms'] - first502['ms'])} "
  f"+ {secs(first502['ms'] - (firstpool['ms'] - OFF))} = {secs(OFF)}")
w("")
w("Corrected sequence of the incident:")
w("")
wto = [r for r in wrk if r["kv"].get("stage") == "db_call_timeout"]
wpe = [r for r in wrk if r["kv"].get("result") == "pool_exhausted"]
firstwpe = min(wpe, key=lambda r: r["ms"])
firstwto = min(wto, key=lambda r: r["ms"])
w(f"1. `{fmt(firstpool['ms'] - OFF)}` database connection pool exhausted "
  f"(`{firstpool['kv']['req']}`, corrected)")
w(f"2. `{fmt(firstwpe['ms'])}` worker records receiving a pool-exhausted "
  f"response (`{firstwpe['kv']['req']}`) and retries")
w(f"3. `{fmt(firstwto['ms'])}` first worker database-call timeout "
  f"(`{firstwto['kv']['req']}`)")
w(f"4. `{fmt(first502['ms'])}` first customer-visible 502 at the edge")
w("")
w("The step that makes the raw reading impossible rather than merely odd:")
w("")
own_db = [r for r in dbreq[firstwpe["kv"]["req"]] if r["kv"].get("msg") == "pool_exhausted"][0]
w(f"- worker recorded the pool-exhausted response for `{firstwpe['kv']['req']}` at "
  f"**{fmt(firstwpe['ms'])}**")
w(f"- the database's own record of that same request's failure is stamped "
  f"**{fmt(own_db['ms'])}**")
w(f"- as recorded the effect precedes its cause by "
  f"**{secs(own_db['ms'] - firstwpe['ms'])} s**; corrected, the cause precedes "
  f"the effect by **{secs(firstwpe['ms'] - (own_db['ms'] - OFF))} s**")
w("")
w(f"- worker retries absorbed the first burst: **{len(wpe)}** requests took a "
  "pool-exhausted response, retried and were answered 200 by the edge")
w(f"- worker database-call timeouts: **{len(wto)}**")
w(f"- lead time: the database was already failing **"
  f"{secs(first502['ms'] - (firstpool['ms'] - OFF))} s** before the first "
  "customer-visible error")
w("")

# ── per-request inversion ────────────────────────────────────────────────
w("## Does the inversion hold request by request?")
w("")
ok = bad = 0
margins = []
for r in five02:
    q = r["kv"]["req"]
    pe = [x for x in dbreq[q] if x["kv"].get("msg") == "pool_exhausted"]
    assert len(pe) == 1, q
    corrected = pe[0]["ms"] - OFF
    if corrected < r["ms"]:
        ok += 1
        margins.append(r["ms"] - corrected)
    else:
        bad += 1
w(f"- of the **{len(five02)}** requests answered 502, the corrected database")
w(f"  failure for the SAME request precedes the edge's 502 in **{ok}** cases and")
w(f"  follows it in **{bad}**")
w(f"- margin range: {secs(min(margins))} to {secs(max(margins))} s")
raw_ok = sum(1 for r in five02
             if [x for x in dbreq[r["kv"]["req"]]
                 if x["kv"].get("msg") == "pool_exhausted"][0]["ms"] < r["ms"])
w(f"- with the raw timestamps the same test puts the database failure first in")
w(f"  **{raw_ok}** of {len(five02)} cases — the inversion is total, not marginal")
w("")

# ── noise that is not evidence ───────────────────────────────────────────
w("## Lines that look like evidence and are not")
w("")
deg = [r for r in api if r["kv"].get("status") == "degraded"]
ps = [r for r in dbl if r["kv"].get("op") == "pool_stats"]
w(f"- `stage=healthcheck` lines in `api.log`: "
  f"{sum(1 for r in api if r['kv'].get('stage') == 'healthcheck')}, of which "
  f"**{len(deg)}** report `status=degraded`. They carry no request id, so they")
w("  cannot be paired across services and contribute nothing to the offset.")
w(f"- `op=pool_stats` lines in `db.log`: **{len(ps)}**; `op=checkpoint` "
  f"{sum(1 for r in dbl if r['kv'].get('op') == 'checkpoint')}; `op=autovacuum` "
  f"{sum(1 for r in dbl if r['kv'].get('op') == 'autovacuum')}. Also unpairable.")
w(f"- `op=heartbeat` lines in `worker.log`: "
  f"{sum(1 for r in wrk if r['kv'].get('op') == 'heartbeat')}.")
w("")
w("## Numbers that appear in no claim")
w("")
w("Individual request ids other than the requeued one, routes, client addresses,")
w("statement names, row counts, queue depths, checkpoint buffer counts and")
w("autovacuum tuple counts are seeded filler. Only the values above are asserted.")

open("GROUND_TRUTH.md", "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
print("wrote GROUND_TRUTH.md")
READBACK

echo "--- sizes ---"
wc -c logs/*.log logs/*.log.* GROUND_TRUTH.md
echo "--- lines ---"
wc -l logs/*.log logs/*.log.*
echo "--- checksums ---"
sha256sum logs/*.log logs/*.log.*
