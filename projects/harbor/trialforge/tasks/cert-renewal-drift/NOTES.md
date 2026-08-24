# NOTES — cert-renewal-drift

## Premise

A Security Engineer is asked by an external audit which TLS certificates in a
240-host estate are actually at risk. The renewal programme has declared its
first wave complete and closed the whole queue behind it. She does not believe
it, because she has seen tickets signed off on somebody's word.

The primary defect is that nine of the 58 closed renewal tickets never resulted
in a deployed certificate. The host still presents the serial its ticket was
raised to *replace*, and the serial the ticket said would be installed appears on
no record anywhere in the inventory, so the certificate was never issued at all.
Five of the nine are already past `not_after` at the assessment instant and four
lapse inside the reporting window; five are production hosts.

Separating the nine is not a two-way join. Of the 58 closed tickets, 45 present the
ticket's target serial directly, 3 present a THIRD serial that `rotation_log.csv`
ties back to the ticket (deployed under the wave, then rotated again out of band),
and 10 still present the replaced serial with a target that was never issued. So a
serial join returns TEN un-landed renewals. But the audit asks which are at risk,
and one of the ten, `identity-idp-01.prod`, presents a certificate valid into 2027:
the renewal stalled but there is no exposure. The real at-risk count is nine; a
serial-only stop at "un-landed" is the confident-wrong answer of ten. The 3 rotated
hosts are the other mis-flag (their original target is also absent, so only the
rotation chain clears them). Genuine renewals total 48.

The cause is in the ticket log, but the closure marker does NOT separate the
groups on its own. All nine at-risk failures carry `closure_evidence=requester_attested`,
yet 16 closed tickets are attested in total: 6 genuine renewals and the stalled-but-
valid phantom were also closed on the owner's word, and the notes field is drawn from
one pool. A plain filter on attestation flags 16 and is wrong by 7; the failures fall
out only from the serial join plus the expiry check. The remediation line is still
that attestation was accepted in place of a
verified rescan, but the marker over-flags rather than cleanly labelling.

The decoy is `media-cdn-02.prod.hbl.example.com`. Its certificate expired
2026-06-24, before any of the nine, and it is a *production* host, so a filter on
`not_after` alone surfaces it. It is not an exposure: withdrawn from service on
2026-06-30, `lifecycle=decommissioned`, and a completed entry in the decommission
register. A plain expiry filter returns seven expired records; six are live
exposures.

The mirror of the decoy is a coverage gap: `notify-worker-02.dr.hbl.example.com`
is active and expired (2026-08-09) but the programme raised NO ticket for it, so
it is invisible from the ticket log and only an estate-wide sweep finds it. It
does appear in the register, but as a `scheduled` withdrawal dated 2026-09-30, in
the future, so it does not clear. The register must be read with status and date,
not as a set: media-cdn-02 (completed) clears, notify-worker-02 (scheduled) does
not. Filtering on `lifecycle` alone is no help either: three decommissioned
records, only one expired.

A re-scan hazard sits underneath all of this: three hosts were re-scanned during
the export and appear in two batches (243 rows, 240 distinct). For one of them the
stale scan still shows the pre-renewal serial, so a naive concatenation that keeps
the earlier row turns a genuine renewal into a false tenth drift host. The
authoritative record is the one with the later `last_observed`, stated in the
scope note; dedup on it before joining.

The clean negative finding is the open queue. Twelve tickets are still open, all
wave two, and every one of the twelve targets a host whose certificate is valid
at the assessment instant and stays valid past the window — zero expired, zero
inside the window. The earliest expiry in the queue is 2026-11-03, 78 days after
the instant and 48 days clear of the window close. The persona has been assuming
the open queue is the risk, so the task asks for that stated positively as a
finding with the count and the date, not left out.

## The frozen instant, and why it is in the fixture

`certs/audit_scope.md` fixes `assessment_as_of = 2026-08-17T00:00:00Z` and
`expiry_window_days = 30`, and states the window end explicitly so no arithmetic
is needed to get it. Every `last_observed` stamp in the inventory is earlier than
that instant; the read-back asserts it. This is the whole reason the prompt stresses
the frozen instant so hard: a task about certificate expiry reads as a task about
*now*, and it is not one. A model that dates the finding from the container clock
gets a different answer to every criterion in phases 2 and 3, and there is no way to
reconcile it with the evidence afterwards. The `time` server that would tempt exactly
that is deliberately not exposed (see Tool surface); the discipline is tested by the
prompt, not by dangling the tool.

Both boundaries are deliberately far from any record, so no off-by-one changes a
count. Nothing in the estate expires between 2026-08-14T20:55:39Z (the last
lapsed host) and 2026-08-21T04:36:02Z (the first inside the window), and the next
expiry after the window closes is 2026-10-06T06:51:29Z, twenty days clear. The
criteria accept either boundary date for the same reason.

## Fixture provenance

All four artefacts are **synthetic and authored here**. Nothing was downloaded
and no real certificate telemetry was used; the hostnames are all under
`example.com`, which is reserved. `environment/fixtures/build_fixture.sh` emits
them and is deterministic: every per-host value is seeded on the hostname rather
than on call order, and serials and fingerprints are truncated SHA-256 of
`hostname|tag`, so generation order cannot change a value. A rebuild from an
empty directory reproduces all eleven artefact sha256s and `GROUND_TRUTH.md`,
verified.

`certs/inventory.csv[.1-.7]` is the estate snapshot: 240 records, one per host,
22 columns — hostname and common name, subject alternative names, issuer DN,
serial, not-before and not-after, key type and size, signature algorithm,
SHA-256 fingerprint, chain depth, environment, owning team, lifecycle, listener
port, protocol, OCSP and CRL URLs, certificate path, discovering scanner and last
observation. It is **exported in eight batches**: `inventory.csv.7` is the first
batch written and `inventory.csv` the last, each repeating the column header, and
read in that order they are one alphabetical host list with no gap and no
overlap. A count taken off one batch is a count of that batch.

`certs/renewal_tickets.csv` is 70 tickets, one per host, with the wave, the
requested and closed dates, the status, the serial being replaced, the serial to
be installed, requester and closer, change window, closure evidence and a note.
`certs/decommissions.csv` is the five-entry withdrawal register.
`certs/audit_scope.md` is the terms of reference carrying the frozen instant.

### The size band, and why it is asserted in the Dockerfile

`task.toml` sets `tool_output_cap = 60000`. The build asserts both halves of the
band and fails if either breaks:

- **every file is under it** — the inventory batches measure 20,473 to 20,940
  bytes, the ticket log 16,304, the register 892 and the scope note 2,032, all
  against the 60,000 ceiling — so any one file reads whole in one tool result.
  Nothing here turns on noticing a truncated read, which would be a cliff rather
  than a gradient.
- **the inventory is far over it** — 165,317 bytes across the eight batches, more
  than 2.7 times the cap — so no single read gets the estate.
  `filesystem_read_multiple_files` across all eight truncates; across two
  batches it is the right tool. That split is the point: the join between 240
  inventory rows and 70 tickets has to be scripted, and every counting criterion
  fails for a reason the answer owns if it is not.

The flagged hosts are pinned to indices that put at least one in every batch —
two in `inventory.csv` and one in each of the other seven — so a model that
reads the newest batch and stops sees two of nine and no way to know it.

**Why the volume is per-record width rather than more hosts.** The obvious way to
grow the corpus is more hosts, and it is wrong here: it makes "nine" harder to
state only by making it longer to count, and it eventually forces another
certificate into the window boundary gaps that keep the counts insensitive to
off-by-one. The volume comes instead from per-record width — fingerprints, OCSP
and CRL URLs, SAN lists, key and signature detail, scanner provenance. None of
it is joinable in a way that changes a scored value.

## Ground-truth read-back

`environment/fixtures/GROUND_TRUTH.md` is **generated**, not written by hand. The
read-back stage at the bottom of `build_fixture.sh` shares no state with the
builder: it re-parses `audit_scope.md` with a regex to recover the instant and
the window and re-derives the window end, globs the batches and sorts them from
the numeric suffix, reads them with its own `csv.DictReader`, asserts the header
is identical across batches, asserts every `last_observed` precedes the instant,
dedups re-scanned hosts to their latest observation (243 rows to 240 hosts),
rebuilds the three-way ticket-to-inventory serial join through the rotation log
from scratch, recomputes the expiry partition, re-derives the decoy and the
uncovered exposure, and recomputes the open-queue extremes. Whatever that stage
prints is the file.

Every value in `tests/reward.toml` came out of that read-back:

- 243 rows across 8 batches resolving to **240** distinct hosts; 70 tickets,
  **58** closed and **12** open
- closure evidence: **requester_attested 16**, **rescan_verified 42**; the marker
  over-flags the failures by 7 and does not partition the closed set
- a serial join returns **10** un-landed renewals; **9** are at-risk exposures and
  the tenth (`identity-idp-01.prod`, certificate valid into 2027) is not, so the
  at-risk count is **9**, not ten
- the **3** superseded hosts cleared through the rotation log, so **48** genuine
  renewals
- **5** already past `not_after` at 2026-08-17, **4** inside the window ending
  2026-09-16
- **7** expired records by date alone against **6** live exposures
- the decoy `media-cdn-02.prod` (completed withdrawal 2026-06-30) and the mirror
  uncovered exposure `notify-worker-02.dr` (no ticket; scheduled withdrawal
  2026-09-30)
- open queue: **12** tickets, **0** expired, **0** inside the window, earliest
  `not_after` **2026-11-03T05:14:22Z**, latest 2027-01-20T21:51:36Z

## Difficulty design

No code-execution server is exposed, so the multi-source join is worked read by
read rather than in one script; that is what carries the tool-call count and denies
the one-shot shortcut a strong model used to collapse the task with. On top of that,
five reinforcing layers, each defeating a different shortcut, tuned so a strong model
passes roughly one run in three:

1. The closure marker no longer separates the groups: 16 attested, only 9 at-risk
   failures, so the serial join is mandatory (and the notes field is one pool).
2. A three-way join: 3 genuine renewals were rotated again after the wave, so a
   serial-only check flags them and the rotation log is needed to clear the 3.
3. A coverage gap plus a scheduled (not completed) withdrawal: one exposure has no
   ticket at all, and register membership must be read with its status and date.
4. Re-scan overlap: 243 rows to 240 hosts, and dedup on `last_observed` is
   required or one genuine renewal reads as a false extra failure.
5. The confounding trap: a serial join returns ten un-landed renewals, but one
   holds a certificate valid into 2027 and is not at risk. The obvious "un-landed =
   at risk" answer of ten is confidently wrong; the expiry check gives the true nine.

The shallow-check hazards remain. `grep -c closed` over the ticket log gives 58
and the wave looks complete by that measure; the defect does not exist inside
either artefact on its own, only in the join. A filter on `not_after` alone gives
seven expired, the most alarming-looking of them a decommissioned production host.
A count taken off the newest batch sees a fraction of the fleet and of the nine.

The one place two artefacts must be joined on a value rather than a key is the
serial: distinguishing "the renewal deployed" from "the host still serves what
the ticket meant to retire" needs the ticket's replaced serial and its target
serial checked against the inventory's current serial, per host. Comparing dates
instead gets the expiry partition right and the flagged set wrong, because the
four hosts inside the window are not yet expired and look ordinary.

## Tool surface

19 exposed across 4 servers, all genuinely usable. filesystem is the primary route;
calculator, desktop-commander and cli-mcp-server are redundant-but-valid routes (they
read the CSVs or do arithmetic), not dead ends. No code-execution server is exposed:
it is deliberately withheld so the join across eight batches, the ticket log, the
rotation log and the register is worked read by read, not collapsed into one script.
Distraction is same-server near-misses plus those redundant paths, with no far-field
dead-end server declared. `sqlite_delete_records` is not exposed, and no unrestricted
shell or process-exec is exposed (`desktop-commander_start_process` and the code
executor are both withheld), so there is no back door to one-shot the task.

Same-server near-misses and redundant routes:

- `filesystem_write_file` / `filesystem_edit_file` — nothing here needs a write, and
  editing the inventory destroys the evidence the answer rests on.
- `filesystem_directory_tree` / `filesystem_get_file_info` / `filesystem_read_media_file`
  — read-shaped near-misses of the list and text-read tools the join actually needs.
- `cli-mcp-server_run_command` — no pipes and `/data` only, so the reflexive
  `cut -d, -f5 | sort | join` is unavailable; a model that commits to the shell path
  has to reimplement the join call by call. Still a real, slower route to read the
  batches.
- `desktop-commander_read_file` / `_list_directory` / `_get_file_info` /
  `_read_multiple_files` / `_start_search` / `_get_more_search_results` and
  `calculator_calculate` — redundant-but-usable paths that read the CSVs or do the
  arithmetic a script would.

Dropped (dead ends, cannot touch the estate in `/data`): `time`, `sqlite` and
`whois` (server-name-recognition distractors), and `mcp-code-executor`, which was
deliberately removed after a run showed a strong model using it to collapse the whole
multi-source join into a handful of calls. Without it the surface is filesystem-heavy
by design.

`filesystem_search_files` is needed because a `*.csv` glob does not match
`inventory.csv.1` — the same trap the fixture's `.gitattributes` covers.

`target_tool_calls = 40` is a walk against the shipped fixture: 3 discovery, 6
spot reads of individual batches and the ticket log, 2 reads of the scope note
and the register, 14-18 scripted passes over the join, and 9-14 cross-checks on
the expiry partition, the decoy, the open queue and the closure-evidence
partition, not an aspiration. Re-measure from `run_summary.json` after the
next live rollout.

## Realism trade

The fixture is cleaner than reality. A real estate snapshot would carry duplicate
hostnames from multiple scanners, hosts presenting more than one certificate,
SAN certificates covering many hosts at once, wildcard entries, expired records
for hosts that no longer resolve, and tickets with more than one host each. The
closure-evidence field in particular is unrealistically tidy: real ticket systems
record closure reasons in free text. The trade is deliberate and it buys full
knowability — every criterion quotes a value read back out of the artefact, with
nothing derived by hand.

The criterion structure would survive a swap to real certificate telemetry,
because each claim describes a *pattern* rather than this incident: a completion
record that a status field cannot falsify, an identifier that only a value join
exposes as stale, an out-of-service asset that a date filter cannot distinguish
from an exposure, and a suspected risk that turns out to be clean. Re-pointing
the fixture would mean re-running the read-back stage and rewriting the numbers;
the phase chain would not change.

## Cross-task overlap

`/data/certs/` is a new path and the task injects nothing into `turing.db` at
all, so there is no collision with the eight baked warehouse tables or with any
other v2 or v3 fixture. It shares the rotated-CSV shape with
`proration-payroll-audit` and the closed-record-versus-reality shape with
`backup-restore-gap`; what differs is that the defect here lives in a join
between two artefacts on a value rather than in one artefact's own series. The
tool allowlist overlaps the other filesystem and code-executor tasks, which is
intended — the allowlist is not a differentiator.

## Not verified

- **No `docker build` of `environment/Dockerfile` on a clean host.** No docker
  daemon is available here. Every assertion in the `RUN` block was instead
  extracted from the Dockerfile, path-rewritten and executed with `sh` against
  the real built artefacts; all twenty pass, and a mutated serial was confirmed
  to fail the block. What is untested is the `FROM` pull and the `COPY` layer.
- **No live rollout.** `target_tool_calls = 40` is a walk, not a measurement, and
  the claim difficulty distribution is a prediction. Both want re-measuring from
  `run_summary.json`.
- **No judge run.** The wording of the tolerances has not been tested against
  `gpt-5.6-luna`. The nine-host naming criterion is the one most likely to need
  loosening, because it names nine values in one assertion; the alternative is
  nine criteria, which would swamp the rest of the reward.
