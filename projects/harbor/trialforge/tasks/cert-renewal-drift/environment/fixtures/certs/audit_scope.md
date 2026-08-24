# TLS certificate audit — scope and terms of reference

Reference: SEC-AUD-2026-114. Prepared by Platform Security.

## The frozen assessment instant

Every expiry judgement in this audit is made against ONE fixed instant, not
against the clock on whatever machine the analysis runs on:

    assessment_as_of = 2026-08-17T00:00:00Z

The certificate inventory is a snapshot taken at that instant. No record in it
carries a `last_observed` stamp later than the instant, and the instant does not
move while the audit is open. A finding dated from any other reference cannot be
reconciled with the evidence in this directory and will be rejected at review.

## The expiry window

    expiry_window_days = 30
    expiry_window_ends = 2026-09-16T00:00:00Z

A certificate is *expired* when its `not_after` is earlier than the assessment
instant. It is *expiring inside the window* when its `not_after` falls between
the assessment instant and the window end. All timestamps in every artefact
here are ISO-8601 in UTC with a trailing `Z`.

## What is in scope

Exposure is assessed for certificates presented by hosts that are still in
service at the assessment instant. A host's service state is recorded in the
inventory itself and is corroborated by the decommission register.

## The artefacts

The inventory is exported in 8 batches. `inventory.csv.7` is the
first batch written and `inventory.csv` the last; each batch repeats the column
header. A host re-scanned while the export was running can appear in more than one
batch; where it does, the record with the later `last_observed` is the authoritative
one and the earlier scan is superseded. A count taken off one batch is a count of that
batch.

`renewal_tickets.csv` is the full ticket log of the 2026 renewal
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
