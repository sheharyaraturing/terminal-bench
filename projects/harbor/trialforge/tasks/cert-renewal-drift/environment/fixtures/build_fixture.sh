#!/bin/bash
# Emits certs/inventory.csv[.1-.7], the ticket log, the decommission register and
# the scope note, then regenerates GROUND_TRUTH.md from them. Why: NOTES.md.

set -euo pipefail
cd "$(dirname "$0")"

rm -rf certs
mkdir -p certs

python3 - <<'BUILD'
import hashlib
import random
from datetime import datetime, timedelta

AS_OF = datetime(2026, 8, 17, 0, 0, 0)          # frozen in certs/audit_scope.md
WINDOW_DAYS = 30
WINDOW_END = AS_OF + timedelta(days=WINDOW_DAYS)
SLICES = 8

SERVICES = ["admin-console", "audit-sink", "billing-api", "catalog-api",
            "checkout-web", "fraud-scorer", "identity-idp", "ledger-core",
            "media-cdn", "notify-worker", "orders-api", "partner-gw",
            "payments-api", "reporting-api", "search-api", "session-store",
            "status-page", "webhook-relay"]
ENVS = ["corp", "dr", "prod", "stage"]

ISSUERS = [
    "CN=Harbourline Internal Issuing CA 2,OU=Platform Security,O=Harbourline Group,C=SE",
    "CN=Harbourline Internal Issuing CA 3,OU=Platform Security,O=Harbourline Group,C=SE",
    "CN=Corvus Public TLS RSA 2026 CA1,O=Corvus Trust Services,C=US",
    "CN=Corvus Public TLS ECC 2026 CA2,O=Corvus Trust Services,C=US",
]
ISSUER_SLUG = ["hbl-issuing-ca2", "hbl-issuing-ca3", "corvus-rsa-ca1", "corvus-ecc-ca2"]
TEAMS = ["commerce-core", "corp-it", "data-platform", "edge-networking",
         "identity", "observability", "payments-platform", "risk-engineering"]
SCANNERS = ["tls-sweep-agent/2.4.1", "tls-sweep-agent/2.4.0", "cert-probe/1.9.3"]
PROTOS = ["https", "grpc-tls", "mtls-internal"]
PEOPLE = ["a.solberg", "b.okonkwo", "c.marchetti", "d.fernandes", "e.haavisto",
          "f.nakamura", "g.pettersen", "h.vasquez", "i.dlamini", "j.karlsson"]
NOTES_CLOSED = [
    "certificate issued and pushed via config management",
    "rotated during the standard Tuesday change window",
    "CSR signed by internal CA; listener reloaded",
    "renewed ahead of the wave deadline",
    "installed with the platform bundle refresh",
]
NOTES_ATTESTED = [
    "owner confirmed completion by email; queue cleared for wave sign-off",
    "closed on owner confirmation at wave cut-off",
    "owner reported done during the wave stand-up",
]
# Lever 1: one merged pool for every closed ticket, so the notes text no longer
# separates drift from genuine the way closure_evidence used to.
NOTES_CLOSED_ALL = NOTES_CLOSED + NOTES_ATTESTED
NOTES_OPEN = [
    "scheduled for the wave two change window",
    "awaiting CSR from the service owner",
    "queued behind the wave two freeze",
]

# ── host list: 240 of the 288 service/env/index combinations, sorted ─────────
combos = [f"{s}-{i:02d}.{e}.hbl.example.com"
          for s in SERVICES for e in ENVS for i in range(1, 5)]
HOSTS = sorted(random.Random(20260817).sample(combos, 240))
assert len(set(HOSTS)) == 240

def rng_for(host, salt=""):
    seed = int(hashlib.sha256((host + "|" + salt).encode()).hexdigest()[:12], 16)
    return random.Random(seed)

def serial(host, tag):
    return hashlib.sha256(f"{host}|{tag}".encode()).hexdigest().upper()[:32]

def fingerprint(host, ser):
    return hashlib.sha256(f"{host}|{ser}|fp".encode()).hexdigest().upper()

def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

# ── roles, pinned to indices so every slice holds part of the answer ─────────
DRIFT_EXPIRED_IX = [6, 70, 95, 123, 187]         # not_after already past AS_OF
DRIFT_WINDOW_IX = [41, 158, 221, 233]            # not_after inside the 30 days
DECOMM_IX = [112, 30, 205]                       # 112 is the expired decoy
assert len(set(DRIFT_EXPIRED_IX + DRIFT_WINDOW_IX + DECOMM_IX)) == 12

DRIFT_IX = DRIFT_EXPIRED_IX + DRIFT_WINDOW_IX
pool = [i for i in range(240) if i not in set(DRIFT_IX + DECOMM_IX)]
pick = random.Random(4711)
OPEN_IX = sorted(pick.sample(pool, 12))
pool = [i for i in pool if i not in set(OPEN_IX)]
DEPLOYED_IX = sorted(pick.sample(pool, 49))
REST_IX = sorted(i for i in pool if i not in set(DEPLOYED_IX))
assert len(REST_IX) == 167

# Lever 1: 6 genuinely-deployed hosts whose ticket was ALSO closed on the owner's
# attestation (truthfully - the renewal did land). Closure evidence then reads
# requester_attested 15, rescan_verified 43; the marker over-flags drift by 6, so
# only the serial join separates the nine failures.
ATTESTED_OK_IX = set(random.Random(9001).sample(DEPLOYED_IX, 6))

# not_after for the nine that never got their new certificate
DRIFT_NOT_AFTER = {
    DRIFT_EXPIRED_IX[0]: datetime(2026, 7, 28, 11, 42, 7),
    DRIFT_EXPIRED_IX[1]: datetime(2026, 8, 2, 6, 19, 51),
    DRIFT_EXPIRED_IX[2]: datetime(2026, 8, 6, 15, 3, 28),
    DRIFT_EXPIRED_IX[3]: datetime(2026, 8, 11, 9, 27, 14),
    DRIFT_EXPIRED_IX[4]: datetime(2026, 8, 14, 20, 55, 39),
    DRIFT_WINDOW_IX[0]: datetime(2026, 8, 21, 4, 36, 2),
    DRIFT_WINDOW_IX[1]: datetime(2026, 8, 29, 13, 48, 45),
    DRIFT_WINDOW_IX[2]: datetime(2026, 9, 4, 7, 11, 30),
    DRIFT_WINDOW_IX[3]: datetime(2026, 9, 11, 18, 24, 9),
}
DECOMM_NOT_AFTER = {
    DECOMM_IX[0]: datetime(2026, 6, 24, 10, 5, 44),      # the decoy: expired
    DECOMM_IX[1]: datetime(2027, 2, 18, 8, 30, 12),
    DECOMM_IX[2]: datetime(2027, 4, 9, 16, 52, 3),
}
DECOMM_ON = {
    DECOMM_IX[0]: "2026-06-30",
    DECOMM_IX[1]: "2026-05-18",
    DECOMM_IX[2]: "2026-07-09",
}

# wave one closure dates; a deployed host's cert is issued on the closure day
WAVE1_FIRST = datetime(2026, 6, 22)
def wave1_dates(host):
    r = rng_for(host, "w1")
    req = WAVE1_FIRST + timedelta(days=r.randrange(0, 29))
    closed = req + timedelta(days=r.randrange(5, 26))
    if closed > datetime(2026, 8, 12):
        closed = datetime(2026, 8, 12)
    return req, closed

# Lever 2: 3 genuinely-deployed hosts rotated AGAIN after wave one, so each now
# presents a third serial. Chosen from early-closing deployed hosts so the later
# rotation still lands before the assessment instant.
def _closed_of(ix):
    _, c = wave1_dates(HOSTS[ix])
    return c
_early = sorted(i for i in DEPLOYED_IX
                if i not in ATTESTED_OK_IX and _closed_of(i) <= datetime(2026, 7, 10))
SUPERSEDED_IX = set(sorted(random.Random(7002).sample(_early, 3)))
SUPERSEDED_HOSTS = {HOSTS[i] for i in SUPERSEDED_IX}

# Lever 3: one active, expired host the renewal programme never raised a ticket for,
# whose only register entry is a FUTURE scheduled withdrawal. A live exposure that is
# invisible from the ticket log and the mirror image of the decommissioned decoy.
UNCOVERED_IX = sorted(random.Random(6001).sample(REST_IX, 1))[0]
UNCOVERED_HOST = HOSTS[UNCOVERED_IX]
ROT_FILLER_IX = sorted(random.Random(7003).sample(
    [i for i in REST_IX if i != UNCOVERED_IX], 11))

def rot_date(host):
    r = rng_for(host, "rotd")
    _, closed = wave1_dates(host)
    return closed + timedelta(days=r.randrange(20, 35))

# Lever 4: three hosts are re-scanned during the export and appear in two batches. The
# record with the later last_observed is authoritative (stated in audit_scope.md). For
# the one deployed host among them the stale copy still shows the PRE-renewal serial, so
# a naive concatenation that keeps the earlier row invents a tenth false drift host.
DUP_DEPLOYED_IX = sorted(random.Random(5001).sample(
    [i for i in DEPLOYED_IX if i not in ATTESTED_OK_IX and i not in SUPERSEDED_IX], 1))[0]
_dup_rest = [i for i in REST_IX if i != UNCOVERED_IX and i not in set(ROT_FILLER_IX)]
DUP_BENIGN_IX = sorted(random.Random(5002).sample(_dup_rest, 2))
DUP_IX = [DUP_DEPLOYED_IX] + DUP_BENIGN_IX

# Confounding trap: one genuinely-deployed host whose renewal ticket was closed but
# never landed - it still presents the serial the ticket meant to replace, and the
# ticket's target was never issued - YET its current certificate is valid well past
# the reporting window. A serial-only join counts it as a tenth failure; the audit
# asks which certificates are AT RISK, and this one is not, so the real count is nine.
# Closed on attestation, so the attested set over-flags all the harder.
PHANTOM_IX = sorted(random.Random(3001).sample(
    [i for i in DEPLOYED_IX if i not in ATTESTED_OK_IX and i not in SUPERSEDED_IX
     and i != DUP_DEPLOYED_IX and i not in set(DUP_BENIGN_IX)], 1))[0]
PHANTOM_HOST = HOSTS[PHANTOM_IX]

OPEN_NOT_AFTER = [datetime(2026, 11, 3, 5, 14, 22), datetime(2026, 11, 14, 12, 6, 9),
                  datetime(2026, 11, 27, 19, 41, 33), datetime(2026, 12, 5, 3, 28, 17),
                  datetime(2026, 12, 12, 22, 9, 48), datetime(2026, 12, 19, 8, 55, 4),
                  datetime(2026, 12, 26, 14, 32, 26), datetime(2027, 1, 2, 6, 47, 11),
                  datetime(2027, 1, 8, 17, 20, 59), datetime(2027, 1, 13, 1, 38, 42),
                  datetime(2027, 1, 17, 11, 4, 15), datetime(2027, 1, 20, 21, 51, 36)]

REST_FIRST = datetime(2026, 10, 5, 0, 0, 0)
REST_LAST = datetime(2027, 6, 20, 0, 0, 0)
rest_span = (REST_LAST - REST_FIRST).days

rows = []
tickets = []

for ix, host in enumerate(HOSTS):
    r = rng_for(host, "inv")
    service = host.split(".")[0].rsplit("-", 1)[0]
    env = host.split(".")[1]
    iss = r.randrange(4)
    lifecycle = "active"
    if ix in DRIFT_NOT_AFTER:
        not_after = DRIFT_NOT_AFTER[ix]
        not_before = not_after - timedelta(days=365)
        ser = serial(host, "old")
    elif ix in DECOMM_NOT_AFTER:
        lifecycle = "decommissioned"
        not_after = DECOMM_NOT_AFTER[ix]
        not_before = not_after - timedelta(days=730)
        ser = serial(host, "legacy")
    elif ix in set(DEPLOYED_IX):
        _, closed = wave1_dates(host)
        if ix in SUPERSEDED_IX:
            rd = rot_date(host)
            not_before = rd + timedelta(hours=r.randrange(1, 23),
                                        minutes=r.randrange(0, 60))
            not_after = not_before + timedelta(days=365)
            ser = serial(host, "rot")
        else:
            not_before = closed + timedelta(hours=r.randrange(1, 23),
                                            minutes=r.randrange(0, 60))
            not_after = not_before + timedelta(days=365)
            ser = serial(host, "new")
    elif ix in set(OPEN_IX):
        not_after = OPEN_NOT_AFTER[sorted(OPEN_IX).index(ix)]
        not_before = not_after - timedelta(days=365)
        ser = serial(host, "current")
    elif ix == UNCOVERED_IX:
        not_after = datetime(2026, 8, 9, 13, 22, 5)     # expired, inside the safe gap
        not_before = not_after - timedelta(days=365)
        ser = serial(host, "current")
    else:
        not_after = REST_FIRST + timedelta(days=r.randrange(0, rest_span),
                                           hours=r.randrange(0, 24),
                                           minutes=r.randrange(0, 60),
                                           seconds=r.randrange(0, 60))
        not_before = not_after - timedelta(days=r.choice([365, 397, 730]))
        ser = serial(host, "current")

    ec = iss == 3
    sans = ";".join([host,
                     f"{service}.{env}.hbl.example.com",
                     f"{host.split('.')[0]}.internal.hbl.example.com"]
                    + ([f"{service}.hbl.example.com"] if r.random() < 0.45 else []))
    rows.append({
        "hostname": host,
        "common_name": host,
        "subject_alt_names": sans,
        "issuer": ISSUERS[iss],
        "serial": ser,
        "not_before": iso(not_before),
        "not_after": iso(not_after),
        "key_type": "EC" if ec else "RSA",
        "key_bits": "384" if ec else r.choice(["2048", "4096"]),
        "signature_algorithm": "ecdsa-with-SHA384" if ec else r.choice(
            ["sha256WithRSAEncryption", "sha384WithRSAEncryption"]),
        "fingerprint_sha256": fingerprint(host, ser),
        "chain_depth": str(r.choice([2, 3])),
        "environment": env,
        "owner_team": TEAMS[r.randrange(len(TEAMS))],
        "lifecycle": lifecycle,
        "listener_port": str(r.choice([443, 6443, 8443, 9443])),
        "protocol": r.choice(PROTOS),
        "ocsp_url": f"http://ocsp.{ISSUER_SLUG[iss]}.example.net",
        "crl_url": f"http://crl.{ISSUER_SLUG[iss]}.example.net/{ISSUER_SLUG[iss]}-{r.randrange(1, 9)}.crl",
        "certificate_path": f"/etc/ssl/certs/{host}.pem",
        "discovered_by": r.choice(SCANNERS),
        "last_observed": iso(datetime(2026, 8, 16, r.randrange(0, 24),
                                      r.randrange(0, 60), r.randrange(0, 60))),
    })

    if ix in set(DEPLOYED_IX) or ix in DRIFT_NOT_AFTER:
        req, closed = wave1_dates(host)
        drifted = ix in DRIFT_NOT_AFTER
        is_phantom = ix == PHANTOM_IX
        tickets.append({
            "wave": "wave-1",
            "host": host,
            "requested_on": req.strftime("%Y-%m-%d"),
            "closed_on": closed.strftime("%Y-%m-%d"),
            "status": "closed",
            # phantom: the ticket names the host's own current serial as the one to
            # replace and a target that was never issued, so it reads as un-landed even
            # though the live certificate is fine. Drift: replaces the live (old) serial.
            # Normal deploy: replaces the retired serial.
            "replaces_serial": serial(host, "new") if is_phantom
                else (ser if drifted else serial(host, "retired")),
            # the wave-1 target is serial(host,"new") for real tickets (for a normal
            # deploy it equals the live serial; for a superseded host it was rotated out;
            # for drift it was never issued). The phantom's target was never issued.
            "target_serial": serial(host, "phantom") if is_phantom else serial(host, "new"),
            "requested_by": PEOPLE[r.randrange(len(PEOPLE))],
            "closed_by": PEOPLE[r.randrange(len(PEOPLE))],
            "change_window": f"CHG-{closed.strftime('%Y%m%d')}-{r.choice('ABC')}",
            "closure_evidence": "requester_attested"
                if (drifted or is_phantom or ix in ATTESTED_OK_IX) else "rescan_verified",
            "notes": r.choice(NOTES_CLOSED_ALL),
        })
    elif ix in set(OPEN_IX):
        req = datetime(2026, 8, 3) + timedelta(days=r.randrange(0, 12))
        tickets.append({
            "wave": "wave-2",
            "host": host,
            "requested_on": req.strftime("%Y-%m-%d"),
            "closed_on": "",
            "status": "open",
            "replaces_serial": ser,
            "target_serial": "",
            "requested_by": PEOPLE[r.randrange(len(PEOPLE))],
            "closed_by": "",
            "change_window": "",
            "closure_evidence": "",
            "notes": r.choice(NOTES_OPEN),
        })

# Drift/deployed is decided by the serial join, not by closure_evidence (lever 1
# breaks that link). A deployed host presents its target_serial; a drift host still
# presents its replaces_serial and the target was never issued anywhere.
live = {r["serial"] for r in rows}
inv_serial = {r["hostname"]: r["serial"] for r in rows}
for t in tickets:
    if t["status"] != "closed":
        continue
    s = inv_serial[t["host"]]
    if s == t["target_serial"]:
        assert t["replaces_serial"] not in live, t["host"]      # deployed: old serial retired
    elif t["host"] in SUPERSEDED_HOSTS:
        assert s == serial(t["host"], "rot"), t["host"]         # deployed then rotated again
        assert t["target_serial"] not in live, t["host"]        # the wave-1 target is retired too
    else:
        assert s == t["replaces_serial"], t["host"]             # drift
        assert t["target_serial"] not in live, t["host"]

tickets.sort(key=lambda t: (t["requested_on"], t["host"]))
for n, t in enumerate(tickets, start=1):
    t["ticket_id"] = f"CRT-{n:04d}"

INV_COLS = list(rows[0].keys())
TKT_COLS = ["ticket_id", "wave", "host", "requested_on", "closed_on", "status",
            "replaces_serial", "target_serial", "requested_by", "closed_by",
            "change_window", "closure_evidence", "notes"]

def csv_line(cols, rec):
    out = []
    for c in cols:
        v = rec[c]
        out.append(f'"{v}"' if ("," in v or ";" in v) else v)
    return ",".join(out)

# Lever 4: the stale re-scan copies. Each is the same host observed a few days earlier;
# the deployed one still shows its pre-renewal serial and an already-expired old cert.
stale_rows = []
for ix in DUP_IX:
    fresh = rows[ix]
    host = fresh["hostname"]
    srec = dict(fresh)
    obs = datetime.strptime(fresh["last_observed"], "%Y-%m-%dT%H:%M:%SZ") \
        - timedelta(days=6, hours=3)
    srec["last_observed"] = iso(obs)
    if ix == DUP_DEPLOYED_IX:
        old_ser = serial(host, "retired")
        old_na = datetime.strptime(fresh["not_before"], "%Y-%m-%dT%H:%M:%SZ") \
            - timedelta(days=4)
        old_nb = old_na - timedelta(days=365)
        srec["serial"] = old_ser
        srec["fingerprint_sha256"] = fingerprint(host, old_ser)
        srec["not_before"] = iso(old_nb)
        srec["not_after"] = iso(old_na)
    stale_rows.append((ix, srec))

# Export batches: inventory.csv.7 is the first batch written, inventory.csv the last.
# 240 fresh rows in 8 batches of 30; each stale copy is appended to a batch 4 away from
# its fresh record, so a host re-scanned during the export appears in two batches.
size = len(rows) // SLICES
assert size * SLICES == len(rows)
batches_out = [rows[k * size:(k + 1) * size] for k in range(SLICES)]
for ix, srec in stale_rows:
    batches_out[(ix // size + 4) % SLICES].append(srec)
for k in range(SLICES):
    suffix = "" if k == SLICES - 1 else f".{SLICES - 1 - k}"
    path = f"certs/inventory.csv{suffix}"
    chunk = batches_out[k]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(",".join(INV_COLS) + "\n")
        for rec in chunk:
            fh.write(csv_line(INV_COLS, rec) + "\n")
    print(f"wrote {path}  {len(chunk)} records")

with open("certs/renewal_tickets.csv", "w", encoding="utf-8", newline="\n") as fh:
    fh.write(",".join(TKT_COLS) + "\n")
    for t in tickets:
        fh.write(csv_line(TKT_COLS, t) + "\n")
print(f"wrote certs/renewal_tickets.csv  {len(tickets)} tickets")

# Lever 3 adds a `status` column: every real withdrawal is `completed`; the uncovered
# host carries a single `scheduled` entry with a FUTURE date, so register membership
# alone does not clear an exposure - the status and date must be read.
DECOMM_EXTRA = [
    ("mail-relay-02.corp.hbl.example.com", "2026-03-11", "CHG-20260311-B",
     "c.marchetti", "relay folded into the managed mail gateway; host destroyed",
     "completed"),
    ("build-cache-01.corp.hbl.example.com", "2026-04-27", "CHG-20260427-A",
     "g.pettersen", "replaced by the shared artefact cache; host destroyed",
     "completed"),
]
with open("certs/decommissions.csv", "w", encoding="utf-8", newline="\n") as fh:
    fh.write("hostname,decommissioned_on,change_ticket,requested_by,notes,status\n")
    reg = [(HOSTS[i], DECOMM_ON[i],
            f"CHG-{DECOMM_ON[i].replace('-', '')[:8]}-C",
            PEOPLE[i % len(PEOPLE)],
            "withdrawn from service; traffic drained and DNS records removed, "
            "listener still answering until the rack is pulled",
            "completed")
           for i in DECOMM_IX] + list(DECOMM_EXTRA)
    reg.append((UNCOVERED_HOST, "2026-09-30", "CHG-20260930-S",
                PEOPLE[UNCOVERED_IX % len(PEOPLE)],
                "withdrawal scheduled; host still in service and answering at the "
                "assessment instant", "scheduled"))
    for h, d, c, p, n, st in sorted(reg, key=lambda x: x[1]):
        fh.write(f"{h},{d},{c},{p},\"{n}\",{st}\n")
print("wrote certs/decommissions.csv")

# Lever 2: the out-of-band rotation log. The 3 superseded hosts are here (their
# wave-1 target became this log's old_serial and the host now shows new_serial);
# the rest are routine rotations of hosts with no wave-1 ticket, so the file is
# context, not an answer key. Every new_serial matches a live inventory serial;
# every old_serial is retired and absent from the inventory.
ROT_COLS = ["hostname", "rotated_on", "old_serial", "new_serial", "reason",
            "change_ticket", "performed_by"]
ROT_REASONS = [
    "issuing-CA batch re-issue after the key-ceremony finding",
    "emergency re-key following the internal CA cross-sign refresh",
    "re-issue after the June crypto-policy update",
    "scheduled annual rotation",
    "listener migrated to the new load balancer, certificate re-cut",
]
rot_rows = []
for j, ix in enumerate(sorted(SUPERSEDED_IX)):
    host = HOSTS[ix]
    rd = rot_date(host)
    rot_rows.append({
        "hostname": host,
        "rotated_on": rd.strftime("%Y-%m-%d"),
        "old_serial": serial(host, "new"),        # the wave-1 target, now retired
        "new_serial": serial(host, "rot"),        # what the host presents at the instant
        "reason": ROT_REASONS[j % 3],
        "change_ticket": f"CHG-{rd.strftime('%Y%m%d')}-R",
        "performed_by": PEOPLE[ix % len(PEOPLE)],
    })
for ix in ROT_FILLER_IX:
    host = HOSTS[ix]
    fr = rng_for(host, "rotf")
    rd = datetime(2026, 5, 1) + timedelta(days=fr.randrange(0, 100))
    rot_rows.append({
        "hostname": host,
        "rotated_on": rd.strftime("%Y-%m-%d"),
        "old_serial": serial(host, "prev"),       # retired, absent from the inventory
        "new_serial": serial(host, "current"),    # matches this host's inventory serial
        "reason": ROT_REASONS[3 + (ix % 2)],
        "change_ticket": f"CHG-{rd.strftime('%Y%m%d')}-R",
        "performed_by": PEOPLE[ix % len(PEOPLE)],
    })
rot_rows.sort(key=lambda x: (x["rotated_on"], x["hostname"]))
with open("certs/rotation_log.csv", "w", encoding="utf-8", newline="\n") as fh:
    fh.write(",".join(ROT_COLS) + "\n")
    for rec in rot_rows:
        fh.write(csv_line(ROT_COLS, rec) + "\n")
print(f"wrote certs/rotation_log.csv  {len(rot_rows)} rotations")

SCOPE = f"""# TLS certificate audit — scope and terms of reference

Reference: SEC-AUD-2026-114. Prepared by Platform Security.

## The frozen assessment instant

Every expiry judgement in this audit is made against ONE fixed instant, not
against the clock on whatever machine the analysis runs on:

    assessment_as_of = {iso(AS_OF)}

The certificate inventory is a snapshot taken at that instant. No record in it
carries a `last_observed` stamp later than the instant, and the instant does not
move while the audit is open. A finding dated from any other reference cannot be
reconciled with the evidence in this directory and will be rejected at review.

## The expiry window

    expiry_window_days = {WINDOW_DAYS}
    expiry_window_ends = {iso(WINDOW_END)}

A certificate is *expired* when its `not_after` is earlier than the assessment
instant. It is *expiring inside the window* when its `not_after` falls between
the assessment instant and the window end. All timestamps in every artefact
here are ISO-8601 in UTC with a trailing `Z`.

## What is in scope

Exposure is assessed for certificates presented by hosts that are still in
service at the assessment instant. A host's service state is recorded in the
inventory itself and is corroborated by the decommission register.

## The artefacts

The inventory is exported in {SLICES} batches. `inventory.csv.{SLICES - 1}` is the
first batch written and `inventory.csv` the last; each batch repeats the column
header. A host re-scanned while the export was running can appear in more than one
batch; where it does, the record with the later `last_observed` is the authoritative
one and the earlier scan is superseded. A count taken off one batch is a count of that
batch.

`renewal_tickets.csv` is the full ticket log of the {AS_OF.year} renewal
programme, both waves. Each ticket names the host it targets, the serial it was
raised to replace, and the serial that was to be installed in its place. Wave
one was declared complete by the programme before this audit opened.

`decommissions.csv` is the register of hosts withdrawn from service. It includes
hosts whose listeners have since been destroyed and no longer appear in any
scan.

`rotation_log.csv` records certificate rotations performed outside the renewal
programme. A host renewed under a wave-one ticket and then rotated again appears
here, and the certificate it now presents is that later rotation's new serial, not
the serial the ticket named.
"""
open("certs/audit_scope.md", "w", encoding="utf-8", newline="\n").write(SCOPE)
print("wrote certs/audit_scope.md")
BUILD

# READ-BACK — own parser, no shared state with the builder above.
# GROUND_TRUTH.md is whatever this stage prints.
python3 - <<'READBACK'
import csv
import glob
import re
from collections import Counter
from datetime import datetime, timedelta

def batches():
    """Inventory batches, first written first: inventory.csv.N ... .1, inventory.csv."""
    rot = sorted(glob.glob("certs/inventory.csv.*"),
                 key=lambda q: -int(q.rsplit(".", 1)[1]))
    return rot + ["certs/inventory.csv"]

scope = open("certs/audit_scope.md", encoding="utf-8").read()
AS_OF = datetime.strptime(
    re.search(r"assessment_as_of = (\S+)", scope).group(1), "%Y-%m-%dT%H:%M:%SZ")
WINDOW_DAYS = int(re.search(r"expiry_window_days = (\d+)", scope).group(1))
WINDOW_END = datetime.strptime(
    re.search(r"expiry_window_ends = (\S+)", scope).group(1), "%Y-%m-%dT%H:%M:%SZ")
assert WINDOW_END == AS_OF + timedelta(days=WINDOW_DAYS)

raw = []
per_batch = []
header = None
for path in batches():
    with open(path, encoding="utf-8", newline="") as fh:
        rdr = csv.DictReader(fh)
        assert header is None or rdr.fieldnames == header, path
        header = rdr.fieldnames
        got = list(rdr)
    per_batch.append((path, len(got)))
    for rec in got:
        rec["_batch"] = path
        raw.append(rec)

def ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
for r in raw:
    assert r["common_name"] == r["hostname"]
    assert ts(r["not_before"]) < ts(r["not_after"])
    assert ts(r["last_observed"]) < AS_OF

# A host re-scanned during the export appears in more than one batch; the record with
# the later last_observed is authoritative and the earlier scan is superseded.
by_host = {}
for rec in sorted(raw, key=lambda r: r["last_observed"]):
    by_host[rec["hostname"]] = rec
inv = list(by_host.values())
n_rescan = len(raw) - len(inv)

with open("certs/renewal_tickets.csv", encoding="utf-8", newline="") as fh:
    tickets = list(csv.DictReader(fh))
with open("certs/decommissions.csv", encoding="utf-8", newline="") as fh:
    decomm = list(csv.DictReader(fh))

closed = [t for t in tickets if t["status"] == "closed"]
opened = [t for t in tickets if t["status"] == "open"]
assert len(closed) + len(opened) == len(tickets)
assert len({t["host"] for t in tickets}) == len(tickets)

with open("certs/rotation_log.csv", encoding="utf-8", newline="") as fh:
    rotations = list(csv.DictReader(fh))
rot_by_old = {row["old_serial"]: row for row in rotations}

live_serials = {r["serial"] for r in inv}
unlanded, landed, superseded = [], [], []
for t in closed:
    rec = by_host[t["host"]]
    s = rec["serial"]
    if s == t["target_serial"]:
        landed.append(t)
    elif t["target_serial"] in rot_by_old and rot_by_old[t["target_serial"]]["new_serial"] == s:
        superseded.append(t)          # deployed, then rotated again out of band
    else:
        assert s == t["replaces_serial"], t["ticket_id"]
        assert t["target_serial"] not in live_serials, t["ticket_id"]
        unlanded.append(t)            # ticket closed but the target serial never landed
genuine = landed + superseded

# An un-landed renewal is only AT RISK if the certificate the host still presents is
# itself expired or expiring inside the window. One un-landed host holds a certificate
# valid well past the window, so it is not an exposure and the audit's real count is
# the rest. This is the trap: a serial-only join stops at "un-landed" and over-counts.
at_risk = [t for t in unlanded if ts(by_host[t["host"]]["not_after"]) <= WINDOW_END]
not_at_risk = [t for t in unlanded if ts(by_host[t["host"]]["not_after"]) > WINDOW_END]
assert len(not_at_risk) == 1, [t["host"] for t in not_at_risk]
drift = at_risk
phantom = not_at_risk[0]

drift.sort(key=lambda t: t["host"])
drift_expired = [t for t in drift if ts(by_host[t["host"]]["not_after"]) < AS_OF]
drift_window = [t for t in drift
                if AS_OF <= ts(by_host[t["host"]]["not_after"]) <= WINDOW_END]
assert len(drift_expired) + len(drift_window) == len(drift)

past = [r for r in inv if ts(r["not_after"]) < AS_OF]
inwin = [r for r in inv if AS_OF <= ts(r["not_after"]) <= WINDOW_END]
decommissioned = [r for r in inv if r["lifecycle"] == "decommissioned"]
decoy = [r for r in past if r["lifecycle"] != "active"]
exposed_past = [r for r in past if r["lifecycle"] == "active"]
ticket_hosts = {t["host"] for t in tickets}
uncovered = [r for r in exposed_past if r["hostname"] not in ticket_hosts]
assert len(uncovered) == 1, [r["hostname"] for r in uncovered]

open_hosts = sorted(opened, key=lambda t: ts(by_host[t["host"]]["not_after"]))
open_earliest = by_host[open_hosts[0]["host"]]

out = []
w = out.append
w("# GROUND_TRUTH.md — cert-renewal-drift")
w("")
w("Everything below was read **back out of the built artefacts** in `certs/` by")
w("the read-back stage of `build_fixture.sh`, which parses them with its own")
w("`csv.DictReader` and shares no state with the builder. `bash build_fixture.sh`")
w("regenerates this file. Every instant is ISO-8601 UTC, as recorded.")
w("")

w("## The frozen assessment instant")
w("")
w(f"- `assessment_as_of` in `certs/audit_scope.md`: **{AS_OF.strftime('%Y-%m-%dT%H:%M:%SZ')}**")
w(f"- `expiry_window_days`: **{WINDOW_DAYS}**; window ends "
  f"**{WINDOW_END.strftime('%Y-%m-%dT%H:%M:%SZ')}**")
w(f"- the latest `last_observed` stamp anywhere in the inventory is "
  f"**{max(r['last_observed'] for r in inv)}**, before the instant")
w("- the instant comes from the artefact, never from the clock: nothing in any")
w("  file names a current time, a timezone other than UTC, or a relative date.")
w("")

w("## Shape")
w("")
w("The inventory is exported in batches. `inventory.csv.7` is the first batch")
w("written and `inventory.csv` the last; each repeats the column header. A count")
w("taken off one batch is a count of that batch, not of the fleet.")
w("")
for path, n in per_batch:
    w(f"- `{path[6:]}`: **{n}** records")
w("")
w(f"- inventory in total: **{len(raw)}** rows across the batches, resolving to "
  f"**{len(inv)}** distinct hosts, **{len(header)}** columns")
w(f"- **{n_rescan}** of those rows are superseded re-scans: a host re-scanned during the")
w("  export appears in two batches, and the record with the later `last_observed` wins")
w(f"- distinct hostnames: **{len({r['hostname'] for r in inv})}**; "
  f"`common_name` equals `hostname` on every record")
w(f"- environments: " + ", ".join(f"{k} {v}" for k, v in
                                  sorted(Counter(r["environment"] for r in inv).items())))
w(f"- lifecycle: " + ", ".join(f"{k} {v}" for k, v in
                               sorted(Counter(r["lifecycle"] for r in inv).items())))
w(f"- `renewal_tickets.csv`: **{len(tickets)}** tickets, "
  f"**{len(closed)}** closed and **{len(opened)}** open, one ticket per host")
w(f"- waves: " + ", ".join(f"{k} {v}" for k, v in
                           sorted(Counter(t["wave"] for t in tickets).items())))
w(f"- closure evidence on closed tickets: " + ", ".join(
    f"{k} {v}" for k, v in sorted(Counter(t["closure_evidence"] for t in closed).items())))
w(f"- `decommissions.csv`: **{len(decomm)}** register entries, of which "
  f"**{sum(1 for d in decomm if d['hostname'] in by_host)}** still appear in the inventory")
w("")

w("## The primary defect — closed tickets whose certificate was never installed")
w("")
w("A closed ticket names the serial it was raised to replace and the serial that")
w("was to be installed. Joining each closed ticket to its host's inventory record,")
w("with `certs/rotation_log.csv` as the third source, splits them three ways:")
w("")
w(f"- **{len(landed)}** closed tickets whose host presents the ticket's `target_serial`")
w("  directly — the renewal deployed and was not touched again")
w(f"- **{len(superseded)}** whose host presents a THIRD serial that `rotation_log.csv`")
w("  ties back to the ticket: deployed, then rotated again out of band, so the ticket's")
w("  `target_serial` is that rotation's `old_serial`. Genuine renewals, not failures.")
w(f"- **{len(genuine)}** genuine renewals in total")
w(f"- **{len(unlanded)}** closed tickets never landed: the host still presents the")
w("  `replaces_serial` and the ticket's `target_serial` was never issued anywhere")
w(f"- of those {len(unlanded)}, only **{len(at_risk)}** are AT RISK — the certificate the host")
w("  still presents is itself expired or expiring inside the window. The other")
w(f"  **{len(not_at_risk)}** presents a certificate valid well past the window, so the renewal")
w("  never landing left no exposure. The audit asks which are at risk, so the answer is")
w(f"  **{len(at_risk)}**, not {len(unlanded)}.")
w(f"- a naive `inventory serial != target_serial` test flags **{len(unlanded) + len(superseded)}**")
w(f"  hosts; the {len(superseded)} superseded clear through the rotation chain and the")
w(f"  {len(not_at_risk)} valid-certificate host is not at risk. `target appears nowhere` is")
w("  true for the un-landed AND the superseded, so it does not separate them on its own.")
n_attested = sum(1 for t in closed if t["closure_evidence"] == "requester_attested")
n_attested_other = n_attested - len(at_risk)
w(f"- all **{len(at_risk)}** at-risk failures carry `closure_evidence=requester_attested`, but")
w(f"  **{n_attested}** closed tickets are attested in total: **{n_attested_other}** more (genuine")
w("  renewals and the un-landed-but-valid host) were also closed on the owner's word. So a")
w(f"  plain filter on the marker flags {n_attested} and is wrong by {n_attested_other}; only the serial")
w("  join plus the expiry check isolate the at-risk failures. The notes field is drawn from")
w("  one pool and does not split them either.")
w("")
w("| host | ticket | closed_on | inventory serial | ticket target_serial | not_after | state at the instant |")
w("|---|---|---|---|---|---|---|")
for t in drift:
    rec = by_host[t["host"]]
    na = ts(rec["not_after"])
    state = "expired" if na < AS_OF else "inside the window"
    w(f"| `{t['host']}` | {t['ticket_id']} | {t['closed_on']} | `{rec['serial']}` | "
      f"`{t['target_serial']}` | `{rec['not_after']}` | {state} |")
w("")
w(f"- of the {len(drift)}: **{len(drift_expired)}** are already past `not_after` "
  f"at the instant, **{len(drift_window)}** expire inside the {WINDOW_DAYS}-day window")
w(f"- every one of the {len(drift)} has `lifecycle=active`")
w(f"- earliest `not_after` among them: **{min(by_host[t['host']]['not_after'] for t in drift)}**")
w(f"- latest `not_after` among them: **{max(by_host[t['host']]['not_after'] for t in drift)}**")
w("")

w("## The superseded renewals — deployed, then rotated again (NOT failures)")
w("")
w(f"These **{len(superseded)}** hosts are the genuine-looking positives a serial-only join")
w("mis-flags. Each was renewed under its wave-one ticket and then rotated a second time")
w("out of band; the chain is `replaces_serial -> target_serial -> rotation new_serial`,")
w("and the inventory `not_before` matches the rotation date, not the ticket closure.")
w("")
w("| host | ticket | target_serial (now retired) | rotation new_serial = inventory serial | rotated_on |")
w("|---|---|---|---|---|")
for t in sorted(superseded, key=lambda t: t["host"]):
    rec = by_host[t["host"]]
    rr = rot_by_old[t["target_serial"]]
    w(f"| `{t['host']}` | {t['ticket_id']} | `{t['target_serial']}` | `{rec['serial']}` | {rr['rotated_on']} |")
w("")

w("## The un-landed renewal that is NOT at risk (the tenth)")
w("")
prec = by_host[phantom["host"]]
w(f"A serial-only join returns **{len(unlanded)}** un-landed tickets, but only "
  f"**{len(at_risk)}** are exposures. The tenth is:")
w("")
w(f"- **`{phantom['host']}`**, ticket {phantom['ticket_id']}: the ticket names "
  f"`{phantom['replaces_serial']}` as the serial to replace and `{phantom['target_serial']}` as")
w("  the one to install, and that target was never issued anywhere, so on serial alone it")
w(f"  reads exactly like a failure. But the certificate the host presents (`{prec['serial']}`)")
w(f"  is valid until **{prec['not_after']}**, well past the window, so the renewal never")
w("  landing left no exposure. It is closed on attestation, so it also sits inside the")
w("  attested set and pushes that marker's over-count higher. Report it as un-landed if")
w("  listing paperwork, but it is NOT one of the at-risk certificates the audit asks for.")
w("")

w("## The decoy — expired but not exposed")
w("")
w(f"Filtering the inventory on `not_after` alone returns **{len(past)}** expired")
w(f"records, one more than the **{len(exposed_past)}** that are live exposures:")
w("")
for r in sorted(past, key=lambda r: r["not_after"]):
    w(f"- `{r['hostname']}` — `not_after` `{r['not_after']}`, "
      f"`lifecycle={r['lifecycle']}`")
w("")
for r in decoy:
    reg = [d for d in decomm if d["hostname"] == r["hostname"]]
    w(f"- the extra record is **`{r['hostname']}`**. Its inventory record says")
    w(f"  `lifecycle={r['lifecycle']}`, and `decommissions.csv` records it withdrawn")
    w(f"  from service on **{reg[0]['decommissioned_on']}** under "
      f"{reg[0]['change_ticket']} — {reg[0]['decommissioned_on'] < r['not_after'][:10] and 'before' or 'after'} "
      f"its certificate expired on {r['not_after'][:10]}.")
    w(f"  It has no renewal ticket of any kind: "
      f"{'present' if any(t['host'] == r['hostname'] for t in tickets) else 'absent'}"
      " from the ticket log.")
w(f"- live exposures already past `not_after`: **{len(exposed_past)}**")
w(f"- decommissioned records in the inventory: **{len(decommissioned)}** — "
  + ", ".join(f"`{r['hostname']}` (`not_after` {r['not_after']})"
              for r in sorted(decommissioned, key=lambda r: r["hostname"])))
w(f"- so filtering on `lifecycle` alone is no better: it returns "
  f"{len(decommissioned)} records of which only {len(decoy)} is expired.")
w("")

u = uncovered[0]
ureg = [d for d in decomm if d["hostname"] == u["hostname"]]
w("## The coverage gap — an exposure with no ticket and only a scheduled withdrawal")
w("")
w(f"- **`{u['hostname']}`** is `lifecycle=active` with `not_after` `{u['not_after']}`,")
w("  already past the instant, and the renewal programme raised **no ticket of any kind**")
w("  for it. It is invisible from the ticket log; only an estate-wide expiry sweep finds it.")
w(f"- it does appear in `decommissions.csv`, but that entry is `status={ureg[0]['status']}`")
w(f"  dated **{ureg[0]['decommissioned_on']}**, which is in the future, so it does NOT clear")
w("  the exposure. Register membership must be read with its status and date, not treated as")
w(f"  a set: `{u['hostname']}` (scheduled, still in service) is a live exposure, while the")
w("  decommissioned decoy above (completed, destroyed) is not.")
w(f"- so the {len(exposed_past)} live exposures are the {len(drift_expired)} drift hosts already")
w(f"  past `not_after` plus this one uncovered host.")
w("")
w(f"- records expiring inside the window: **{len(inwin)}**, all of them "
  f"{'drift hosts' if {r['hostname'] for r in inwin} == {t['host'] for t in drift_window} else 'MIXED'}")
nxt = sorted((ts(r["not_after"]), r["hostname"]) for r in inv
             if ts(r["not_after"]) > WINDOW_END)
w(f"- the next `not_after` after the window closes is "
  f"**{nxt[0][0].strftime('%Y-%m-%dT%H:%M:%SZ')}** (`{nxt[0][1]}`), so neither")
w("  boundary is close to another record and no off-by-one day changes a count.")
w("")

w("## The clean negative finding — the open queue is not the risk")
w("")
w(f"- tickets still open: **{len(opened)}**, all `wave-2`")
w(f"- of those {len(opened)} hosts, **{sum(1 for t in opened if ts(by_host[t['host']]['not_after']) > WINDOW_END)}** "
  f"have a certificate whose `not_after` is later than the window end")
w(f"- expired among them: **{sum(1 for t in opened if ts(by_host[t['host']]['not_after']) < AS_OF)}**; "
  f"inside the window: **{sum(1 for t in opened if AS_OF <= ts(by_host[t['host']]['not_after']) <= WINDOW_END)}**")
w(f"- earliest `not_after` in the open queue: **{open_earliest['not_after']}** on "
  f"`{open_earliest['hostname']}`, which is "
  f"**{(ts(open_earliest['not_after']) - AS_OF).days}** days after the instant and "
  f"**{(ts(open_earliest['not_after']) - WINDOW_END).days}** days after the window closes")
w(f"- latest `not_after` in the open queue: "
  f"**{max(by_host[t['host']]['not_after'] for t in opened)}**")
w("- every open ticket therefore covers a certificate that is still valid at the")
w("  instant and stays valid past the window. The open queue is a real backlog")
w("  and not an exposure.")
w("")

w("## Counts that a shallow read gets wrong")
w("")
w(f"- `grep -c closed` over the ticket log gives {len(closed)}, and the programme's")
w(f"  wave-one queue is complete by that measure. The defect is invisible without")
w("  the join to the inventory.")
w(f"- filtering `not_after` alone gives {len(past)} expired and {len(inwin)} inside the")
w(f"  window; the exposure figures are {len(exposed_past)} and {len(drift_window)}.")
w(f"- a count taken off `inventory.csv` alone sees {per_batch[-1][1]} of {len(inv)} records")
w(f"  and {sum(1 for t in drift if by_host[t['host']]['_batch'] == 'certs/inventory.csv')} "
  f"of the {len(drift)} drift hosts.")
w("- drift hosts by batch: " + ", ".join(
    f"{k[6:]} {v}" for k, v in sorted(Counter(
        by_host[t["host"]]["_batch"] for t in drift).items())) + " — every batch holds at least one.")
w(f"- **{n_rescan}** hosts appear in two batches; keeping the earlier scan rather than the")
w("  later one flips one genuine renewal into a false tenth drift host. Dedup on")
w("  `last_observed` before joining the tickets.")
w("")

w("## Numbers that appear in no claim")
w("")
w("Fingerprints, key types and sizes, signature algorithms, chain depths, OCSP")
w("and CRL URLs, certificate paths, scanner versions, listener ports, protocols,")
w("owner teams, subject alternative names, requester and closer initials, change")
w("window ids and ticket notes are seeded filler. Only the values above are")
w("asserted.")

open("GROUND_TRUTH.md", "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
print("wrote GROUND_TRUTH.md")
READBACK

echo "--- per-file sizes ---"
wc -c certs/* | sort -n
echo "--- inventory total ---"
cat certs/inventory.csv* | wc -c
echo "--- line counts ---"
wc -l certs/*
echo "--- checksums ---"
sha256sum certs/*
