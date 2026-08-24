# GROUND_TRUTH.md — cert-renewal-drift

Everything below was read **back out of the built artefacts** in `certs/` by
the read-back stage of `build_fixture.sh`, which parses them with its own
`csv.DictReader` and shares no state with the builder. `bash build_fixture.sh`
regenerates this file. Every instant is ISO-8601 UTC, as recorded.

## The frozen assessment instant

- `assessment_as_of` in `certs/audit_scope.md`: **2026-08-17T00:00:00Z**
- `expiry_window_days`: **30**; window ends **2026-09-16T00:00:00Z**
- the latest `last_observed` stamp anywhere in the inventory is **2026-08-16T23:47:07Z**, before the instant
- the instant comes from the artefact, never from the clock: nothing in any
  file names a current time, a timezone other than UTC, or a relative date.

## Shape

The inventory is exported in batches. `inventory.csv.7` is the first batch
written and `inventory.csv` the last; each repeats the column header. A count
taken off one batch is a count of that batch, not of the fleet.

- `inventory.csv.7`: **30** records
- `inventory.csv.6`: **30** records
- `inventory.csv.5`: **31** records
- `inventory.csv.4`: **30** records
- `inventory.csv.3`: **31** records
- `inventory.csv.2`: **30** records
- `inventory.csv.1`: **30** records
- `inventory.csv`: **31** records

- inventory in total: **243** rows across the batches, resolving to **240** distinct hosts, **22** columns
- **3** of those rows are superseded re-scans: a host re-scanned during the
  export appears in two batches, and the record with the later `last_observed` wins
- distinct hostnames: **240**; `common_name` equals `hostname` on every record
- environments: corp 61, dr 59, prod 58, stage 62
- lifecycle: active 237, decommissioned 3
- `renewal_tickets.csv`: **70** tickets, **58** closed and **12** open, one ticket per host
- waves: wave-1 58, wave-2 12
- closure evidence on closed tickets: requester_attested 16, rescan_verified 42
- `decommissions.csv`: **6** register entries, of which **4** still appear in the inventory

## The primary defect — closed tickets whose certificate was never installed

A closed ticket names the serial it was raised to replace and the serial that
was to be installed. Joining each closed ticket to its host's inventory record,
with `certs/rotation_log.csv` as the third source, splits them three ways:

- **45** closed tickets whose host presents the ticket's `target_serial`
  directly — the renewal deployed and was not touched again
- **3** whose host presents a THIRD serial that `rotation_log.csv`
  ties back to the ticket: deployed, then rotated again out of band, so the ticket's
  `target_serial` is that rotation's `old_serial`. Genuine renewals, not failures.
- **48** genuine renewals in total
- **10** closed tickets never landed: the host still presents the
  `replaces_serial` and the ticket's `target_serial` was never issued anywhere
- of those 10, only **9** are AT RISK — the certificate the host
  still presents is itself expired or expiring inside the window. The other
  **1** presents a certificate valid well past the window, so the renewal
  never landing left no exposure. The audit asks which are at risk, so the answer is
  **9**, not 10.
- a naive `inventory serial != target_serial` test flags **13**
  hosts; the 3 superseded clear through the rotation chain and the
  1 valid-certificate host is not at risk. `target appears nowhere` is
  true for the un-landed AND the superseded, so it does not separate them on its own.
- all **9** at-risk failures carry `closure_evidence=requester_attested`, but
  **16** closed tickets are attested in total: **7** more (genuine
  renewals and the un-landed-but-valid host) were also closed on the owner's word. So a
  plain filter on the marker flags 16 and is wrong by 7; only the serial
  join plus the expiry check isolate the at-risk failures. The notes field is drawn from
  one pool and does not split them either.

| host | ticket | closed_on | inventory serial | ticket target_serial | not_after | state at the instant |
|---|---|---|---|---|---|---|
| `admin-console-03.prod.hbl.example.com` | CRT-0017 | 2026-07-20 | `352112C989A614BCB0D0A2A8B40E5F10` | `5AF4B81220166ADAD78A266A0B25DE1C` | `2026-07-28T11:42:07Z` | expired |
| `catalog-api-01.dr.hbl.example.com` | CRT-0008 | 2026-07-05 | `070BF26F4AD160F2CE300ACB409AF511` | `0B3AC1D3CC2245DBFD5052175AFD5DDF` | `2026-08-21T04:36:02Z` | inside the window |
| `fraud-scorer-01.prod.hbl.example.com` | CRT-0053 | 2026-07-30 | `A3782771A64AB5EF2C2EDFA459474A83` | `56961E16D07B819A9D1237E4FD92849A` | `2026-08-02T06:19:51Z` | expired |
| `identity-idp-04.prod.hbl.example.com` | CRT-0056 | 2026-08-02 | `26F6C7C7106F23294938F7F0CAB70A47` | `413ED17CA0FB41B2235E331D68395F72` | `2026-08-06T15:03:28Z` | expired |
| `notify-worker-01.stage.hbl.example.com` | CRT-0031 | 2026-07-28 | `A9D3FA25F8E846704646BC2921D0269B` | `D58AAFD3285EC6D755FC6764A131D492` | `2026-08-11T09:27:14Z` | expired |
| `partner-gw-04.prod.hbl.example.com` | CRT-0049 | 2026-07-26 | `16459D182319F68371EDCE4D559D812B` | `E4523912BCEB98407DD96C94583D239C` | `2026-08-29T13:48:45Z` | inside the window |
| `search-api-01.corp.hbl.example.com` | CRT-0042 | 2026-07-31 | `193FDAA3192D7CCF37E6B0D42A38B926` | `363609FF8B2DB03C1C1C411D757F0D4E` | `2026-08-14T20:55:39Z` | expired |
| `status-page-03.prod.hbl.example.com` | CRT-0007 | 2026-07-07 | `FCE4D4CF9DC97FDC825C5A1F91EBBFA2` | `87F17727433945564C1A318184F72F8D` | `2026-09-04T07:11:30Z` | inside the window |
| `webhook-relay-03.corp.hbl.example.com` | CRT-0051 | 2026-08-07 | `14BE6CE916F3B0B4B271F5EABF405E4A` | `B3CF6F42380B956C338F62F07A7DA3A9` | `2026-09-11T18:24:09Z` | inside the window |

- of the 9: **5** are already past `not_after` at the instant, **4** expire inside the 30-day window
- every one of the 9 has `lifecycle=active`
- earliest `not_after` among them: **2026-07-28T11:42:07Z**
- latest `not_after` among them: **2026-09-11T18:24:09Z**

## The superseded renewals — deployed, then rotated again (NOT failures)

These **3** hosts are the genuine-looking positives a serial-only join
mis-flags. Each was renewed under its wave-one ticket and then rotated a second time
out of band; the chain is `replaces_serial -> target_serial -> rotation new_serial`,
and the inventory `not_before` matches the rotation date, not the ticket closure.

| host | ticket | target_serial (now retired) | rotation new_serial = inventory serial | rotated_on |
|---|---|---|---|---|
| `admin-console-01.prod.hbl.example.com` | CRT-0010 | `FA8741E35213FFACD69D5EC493F9F1AD` | `46E4C4EE8166C7B76FD8FF57A7AAABFC` | 2026-08-03 |
| `partner-gw-01.stage.hbl.example.com` | CRT-0013 | `559B6192BFB97FADAE979B3BC889A1B2` | `8EDB7871316E28A64850683881DD7E9E` | 2026-08-01 |
| `session-store-03.dr.hbl.example.com` | CRT-0006 | `4EFBF22ECDBE27E7BD663D443C934CFB` | `CDD2E8253D79873639C1867208AC29D9` | 2026-08-08 |

## The un-landed renewal that is NOT at risk (the tenth)

A serial-only join returns **10** un-landed tickets, but only **9** are exposures. The tenth is:

- **`identity-idp-01.prod.hbl.example.com`**, ticket CRT-0045: the ticket names `F919DBA1097C3F1C1A159A7C68258D3A` as the serial to replace and `17BA720509E6B2114EDB3D8A0807F049` as
  the one to install, and that target was never issued anywhere, so on serial alone it
  reads exactly like a failure. But the certificate the host presents (`F919DBA1097C3F1C1A159A7C68258D3A`)
  is valid until **2027-07-23T09:11:00Z**, well past the window, so the renewal never
  landing left no exposure. It is closed on attestation, so it also sits inside the
  attested set and pushes that marker's over-count higher. Report it as un-landed if
  listing paperwork, but it is NOT one of the at-risk certificates the audit asks for.

## The decoy — expired but not exposed

Filtering the inventory on `not_after` alone returns **7** expired
records, one more than the **6** that are live exposures:

- `media-cdn-02.prod.hbl.example.com` — `not_after` `2026-06-24T10:05:44Z`, `lifecycle=decommissioned`
- `admin-console-03.prod.hbl.example.com` — `not_after` `2026-07-28T11:42:07Z`, `lifecycle=active`
- `fraud-scorer-01.prod.hbl.example.com` — `not_after` `2026-08-02T06:19:51Z`, `lifecycle=active`
- `identity-idp-04.prod.hbl.example.com` — `not_after` `2026-08-06T15:03:28Z`, `lifecycle=active`
- `notify-worker-02.dr.hbl.example.com` — `not_after` `2026-08-09T13:22:05Z`, `lifecycle=active`
- `notify-worker-01.stage.hbl.example.com` — `not_after` `2026-08-11T09:27:14Z`, `lifecycle=active`
- `search-api-01.corp.hbl.example.com` — `not_after` `2026-08-14T20:55:39Z`, `lifecycle=active`

- the extra record is **`media-cdn-02.prod.hbl.example.com`**. Its inventory record says
  `lifecycle=decommissioned`, and `decommissions.csv` records it withdrawn
  from service on **2026-06-30** under CHG-20260630-C — after its certificate expired on 2026-06-24.
  It has no renewal ticket of any kind: absent from the ticket log.
- live exposures already past `not_after`: **6**
- decommissioned records in the inventory: **3** — `billing-api-02.dr.hbl.example.com` (`not_after` 2027-02-18T08:30:12Z), `media-cdn-02.prod.hbl.example.com` (`not_after` 2026-06-24T10:05:44Z), `session-store-03.corp.hbl.example.com` (`not_after` 2027-04-09T16:52:03Z)
- so filtering on `lifecycle` alone is no better: it returns 3 records of which only 1 is expired.

## The coverage gap — an exposure with no ticket and only a scheduled withdrawal

- **`notify-worker-02.dr.hbl.example.com`** is `lifecycle=active` with `not_after` `2026-08-09T13:22:05Z`,
  already past the instant, and the renewal programme raised **no ticket of any kind**
  for it. It is invisible from the ticket log; only an estate-wide expiry sweep finds it.
- it does appear in `decommissions.csv`, but that entry is `status=scheduled`
  dated **2026-09-30**, which is in the future, so it does NOT clear
  the exposure. Register membership must be read with its status and date, not treated as
  a set: `notify-worker-02.dr.hbl.example.com` (scheduled, still in service) is a live exposure, while the
  decommissioned decoy above (completed, destroyed) is not.
- so the 6 live exposures are the 5 drift hosts already
  past `not_after` plus this one uncovered host.

- records expiring inside the window: **4**, all of them drift hosts
- the next `not_after` after the window closes is **2026-10-06T06:51:29Z** (`audit-sink-02.stage.hbl.example.com`), so neither
  boundary is close to another record and no off-by-one day changes a count.

## The clean negative finding — the open queue is not the risk

- tickets still open: **12**, all `wave-2`
- of those 12 hosts, **12** have a certificate whose `not_after` is later than the window end
- expired among them: **0**; inside the window: **0**
- earliest `not_after` in the open queue: **2026-11-03T05:14:22Z** on `admin-console-04.dr.hbl.example.com`, which is **78** days after the instant and **48** days after the window closes
- latest `not_after` in the open queue: **2027-01-20T21:51:36Z**
- every open ticket therefore covers a certificate that is still valid at the
  instant and stays valid past the window. The open queue is a real backlog
  and not an exposure.

## Counts that a shallow read gets wrong

- `grep -c closed` over the ticket log gives 58, and the programme's
  wave-one queue is complete by that measure. The defect is invisible without
  the join to the inventory.
- filtering `not_after` alone gives 7 expired and 4 inside the
  window; the exposure figures are 6 and 4.
- a count taken off `inventory.csv` alone sees 31 of 240 records
  and 2 of the 9 drift hosts.
- drift hosts by batch: inventory.csv 2, inventory.csv.1 1, inventory.csv.2 1, inventory.csv.3 1, inventory.csv.4 1, inventory.csv.5 1, inventory.csv.6 1, inventory.csv.7 1 — every batch holds at least one.
- **3** hosts appear in two batches; keeping the earlier scan rather than the
  later one flips one genuine renewal into a false tenth drift host. Dedup on
  `last_observed` before joining the tickets.

## Numbers that appear in no claim

Fingerprints, key types and sizes, signature algorithms, chain depths, OCSP
and CRL URLs, certificate paths, scanner versions, listener ports, protocols,
owner teams, subject alternative names, requester and closer initials, change
window ids and ticket notes are seeded filler. Only the values above are
asserted.
