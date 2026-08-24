# Records Retention Schedule — RS-2026.1

Owner: Data Governance Office
Status: in force
Effective: 2026-01-15
Supersedes: RS-2025.3

## 1. Scope

This schedule governs every record class held in the platform record inventory.
Backup snapshots and disaster-recovery copies are out of scope; they are governed
by BR-2024.2 and must not be included in any figure reported under this schedule.

## 2. How the windows are applied

2.1  Compliance is assessed at a fixed instant, not continuously. For the current
     reporting cycle that instant — the snapshot instant — is
     **2026-04-01T00:00:00Z**. Every determination made under this schedule is
     made as of that instant. It does not move with the wall clock of whoever is
     running the assessment.

2.2  Retention is measured from the record's creation timestamp. Inventory
     timestamps are written by the originating region and carry that region's UTC
     offset. All arithmetic under this schedule is performed in Coordinated
     Universal Time, so a creation timestamp must be normalised to UTC before its
     age is computed. Comparing the local wall-clock portion of a timestamp
     against a UTC cut-off is not a valid determination and has previously
     produced both false positives and false negatives in the same cycle.

2.3  Windows are stated in calendar days, counted from creation to the snapshot
     instant. A record becomes eligible for destruction once its age EXCEEDS its
     window. A record whose age equals its window exactly is not yet eligible and
     is carried into the next cycle.

2.4  A record under legal hold is exempt from scheduled destruction for as long as
     the hold is in force, whatever its age. A hold neither extends nor shortens
     the underlying window: on release, the record is assessed against its
     original creation timestamp. Held records are reported separately and must
     never appear on a destruction list.

## 3. Class windows

### 3.1 Transaction logs — `txn_log`

Retention: **90 days**. Operational payment and ledger event logs emitted by the
transaction pipeline.

### 3.2 Support correspondence — `support_corr`

Retention: **540 days**. Inbound and outbound customer support messages,
including attachments and internal notes on the thread.

### 3.3 Marketing contact records — `marketing_contact`

Retention: **1,095 days** (36 months). Consent records, campaign membership and
suppression-list entries.

### 3.4 Audit trail events — `audit_trail`

Retention: **2,555 days** (7 years). Authentication, authorisation and
administrative action events. This is a statutory minimum and must not be
shortened for storage reasons.

### 3.5 Recruitment applicant files — `hr_applicant`

Retention: **730 days**. Applications, interview notes and assessment scores for
candidates not subsequently employed.

### 3.6 Session replay bundles — `session_replay`

Session replay bundles are a derived artefact of a support interaction and are
not separately scheduled: a bundle is retained for the same period as the support
correspondence it was captured alongside, and is assessed under §3.2. Bundles are
not un-scheduled, are not indefinitely retained, and are not exempt from §2.4.

## 4. Reporting

Each cycle the Data Governance Office reports, per class: the number of records
past window at the snapshot instant, the number of those withheld under §2.4, and
the resulting destruction list. Over-statement of the backlog is a reportable
control failure in its own right, on the same footing as failure to destroy.
