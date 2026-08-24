#!/bin/bash
# ORACLE — must satisfy every criterion in tests/reward.toml. Write BOTH paths:
# a separate verifier only reads /logs/artifacts. Figures: GROUND_TRUTH.md.
set -euo pipefail
mkdir -p /logs/agent /logs/artifacts

tee /logs/agent/final_answer.txt /logs/artifacts/final_answer.txt <<'EOF'
Nadia, your instinct was right. Nine renewals were signed off and never deployed.
Here is the whole thing, with the numbers you can defend on Friday.

THE REFERENCE INSTANT

Every date below is measured against the instant the audit's terms of reference
fix, which is 2026-08-17T00:00:00Z, with a thirty-day reporting window closing
2026-09-16T00:00:00Z. Nothing here is dated from a machine clock. The latest
observation stamp anywhere in the snapshot sits before the instant, so the two
are consistent.

WHAT I WORKED FROM

The estate snapshot is 240 hosts, handed over in eight export batches. A few
hosts were re-scanned while the export was running and appear in two batches; I
resolved each of those to the record with the later last_observed before joining
anything, because keeping the earlier scan would have invented a tenth false
failure. Everything below is a join across the whole export against the renewal
programme's full ticket log, which holds 70 tickets, one per host: 58 closed and
12 still open.

1. THE NINE AT RISK (closed renewal never landed, and the certificate is expiring)

  admin-console-03.prod.hbl.example.com     ticket CRT-0017
  catalog-api-01.dr.hbl.example.com         ticket CRT-0008
  fraud-scorer-01.prod.hbl.example.com      ticket CRT-0053
  identity-idp-04.prod.hbl.example.com      ticket CRT-0056
  notify-worker-01.stage.hbl.example.com    ticket CRT-0031
  partner-gw-04.prod.hbl.example.com        ticket CRT-0049
  search-api-01.corp.hbl.example.com        ticket CRT-0042
  status-page-03.prod.hbl.example.com       ticket CRT-0007
  webhook-relay-03.corp.hbl.example.com     ticket CRT-0051

Nine hosts. Five of them are production.

2. HOW I SEPARATED THEM FROM THE RENEWALS THAT REALLY HAPPENED

Every ticket names two serials: the one it was raised to replace, and the one
that was to be installed in its place. Joining each closed ticket to its host's
current certificate, with the rotation log as a third source, splits the 58.

  45 closed tickets: the host presents the serial the ticket said would be
     installed. Those renewals happened and were not touched again.

   3 closed tickets: the host presents a THIRD serial, neither the replaced one
     nor the ticket's target. These are genuine renewals that were rotated AGAIN
     after wave one, so a plain serial check would wrongly flag them. The
     rotation log clears each one: the ticket's target serial is that later
     rotation's old serial, and the host now presents the rotation's new serial.
     They are:

       admin-console-01.prod.hbl.example.com    ticket CRT-0010  rotated 2026-08-03
       partner-gw-01.stage.hbl.example.com      ticket CRT-0013  rotated 2026-08-01
       session-store-03.dr.hbl.example.com      ticket CRT-0006  rotated 2026-08-08

     That makes 48 genuine renewals in total. That is the answer to "how do you
     know the ones you are not flagging are fine": not by sampling, but by
     tracing every installed serial back to its ticket, through the rotation log
     where a host was rotated a second time.

  10 closed tickets: the host still presents the serial the ticket was raised to
     REPLACE, and the ticket's target serial appears on no host anywhere in the
     estate, so the renewal never landed. But "never landed" is not "at risk", and
     one of these ten is not a risk at all, so the count that goes in the audit is
     NINE, not ten. The one to hold back:

THE TENTH UN-LANDED RENEWAL IS NOT AT RISK

identity-idp-01.prod.hbl.example.com reads exactly like a failure on serial alone:
it still presents the serial its ticket meant to replace, and the ticket's target
was never issued anywhere. But the certificate it is actually serving is valid
until 2027-07-23, almost a year of runway. The renewal stalling is a housekeeping
item, not an exposure. It was closed on the owner's attestation, which is part of
why that marker over-counts. Report it as an un-landed renewal if you are listing
paperwork, but it is NOT one of the certificates at risk, which is why the at-risk
list is nine and the serial-only count of ten is wrong.

The stronger version of the serial test: for all ten un-landed hosts the serial the
ticket said would be installed appears on no host anywhere. That test alone does not
clear the three rotated hosts (their original target is also absent now) and does
not tell you which un-landed hosts are actually exposures; the expiry check does.

3. THE EXPOSURE, SPLIT

Already lapsed at the assessment instant, five hosts:

  admin-console-03.prod     expired 2026-07-28T11:42:07Z
  fraud-scorer-01.prod      expired 2026-08-02T06:19:51Z
  identity-idp-04.prod      expired 2026-08-06T15:03:28Z
  notify-worker-01.stage    expired 2026-08-11T09:27:14Z
  search-api-01.corp        expired 2026-08-14T20:55:39Z

Lapsing inside the reporting window, on or before 2026-09-16, four hosts:

  catalog-api-01.dr         lapses 2026-08-21T04:36:02Z
  partner-gw-04.prod        lapses 2026-08-29T13:48:45Z
  status-page-03.prod       lapses 2026-09-04T07:11:30Z
  webhook-relay-03.corp     lapses 2026-09-11T18:24:09Z

Five and four. The split is not sensitive to how the window boundary is counted:
nothing in the estate expires between 2026-08-14 and 2026-08-21, and the next
expiry after the window closes is well clear of it.

4. WHAT LOOKS EXPIRED AND IS NOT, AND WHAT THE TICKET LOG MISSED

Filter the estate on expiry date alone and you get seven expired certificates.
Six of those are live exposures. Reconcile carefully in both directions.

One expired record is NOT an exposure:

  media-cdn-02.prod.hbl.example.com — certificate expired 2026-06-24T10:05:44Z

That host has been withdrawn from service. Two independent things say so: its own
record carries a decommissioned service state rather than an active one (the only
expired record in the snapshot that does), and the decommission register carries
it as a completed withdrawal on 2026-06-30 under change CHG-20260630-C. Exclude
it. So seven expired by date, six live exposures. Report the six, not the seven.

Now the other direction, because the ticket log does not catch everything. One of
those six live exposures never had a renewal ticket raised for it at all:

  notify-worker-02.dr.hbl.example.com — certificate expired 2026-08-09T13:22:05Z,
  host still active and in service, and NO ticket in either wave.

It is a real exposure that the whole ticket-based analysis is blind to; only an
estate-wide expiry sweep finds it. And do not let the register wave it away: it
does appear there, but that entry is only a SCHEDULED withdrawal dated
2026-09-30, in the future, so the host is still in service now and the exposure
stands. Register membership has to be read with its status and date, not treated
as a set: media-cdn-02 is a completed withdrawal and clears; notify-worker-02 is
a scheduled one and does not.

So the six live exposures are the five lapsed drift hosts above plus this one
uncovered host.

5. THE OPEN QUEUE IS NOT THE RISK

There are 12 tickets still open, all of them second wave. Every one of the 12
targets a host whose certificate is valid at the assessment instant and stays
valid well past the reporting window. None is expired and none lapses inside the
window. The earliest expiry anywhere in the open queue is 2026-11-03T05:14:22Z,
on admin-console-04.dr.hbl.example.com, which is 78 days after the instant and 48
clear days after the window closes. The latest runs to 2027-01-20.

The open queue is a real backlog with lead time in hand. It is not the exposure.
The exposure is in the queue that was already closed.

6. WHAT LET IT THROUGH

All nine at-risk failures were closed on the requester's own attestation that the
work was done, with no verified rescan of the host. But the closure marker on its
own does not find them: 16 closed tickets were closed on attestation, and only 9 of
those are at-risk failures. The other 7 were genuine renewals, or the stalled-but-
valid identity-idp-01.prod, that also happened to be signed off on the owner's word.
So a plain filter on the ticket log would flag 16 and be wrong by 7; the failures
only fall out of the serial join plus the expiry check. That is exactly why the
scan matters and why the attestation path cannot stand in for it.

For the remediation section: closure on requester attestation was accepted as
equivalent to a verified rescan, so renewals were recorded complete without
anything checking the host. Make rescan confirmation of the target serial the
only closure path.

WHAT I WOULD PUT IN THE AUDIT RESPONSE

Nine certificates at risk from wave one: five already lapsed as of 2026-08-17,
four lapsing on or before 2026-09-16, five of them production. A serial-only join
returns ten un-landed renewals, but identity-idp-01.prod is not a risk - its
certificate is valid into 2027 - so the at-risk list is nine, not ten. Three
further wave-one hosts look unrenewed on a serial check but were rotated again and
are fine, cleared through the rotation log, so the genuine total is 48 of 58 closed.
Separately, one active host, notify-worker-02.dr, is an expired live exposure the
programme never raised a ticket for, and its register entry is only a scheduled
withdrawal so it does not clear. A plain expiry filter returns seven; the real
live-exposure count is six once the decommissioned media-cdn-02 is set aside. The
12 open tickets are not an exposure and the earliest has until 2026-11-03. Root
cause is the attestation closure path, which over-flags on its own and only the
scan against installed serials plus the expiry check separates the real failures.
EOF
