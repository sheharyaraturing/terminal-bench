#!/bin/bash
# Oracle answer for the retention-purge-gap acceptance gate.
set -euo pipefail
mkdir -p /logs/agent /logs/artifacts

tee /logs/agent/final_answer.txt /logs/artifacts/final_answer.txt <<'EOF'
The defensible assessment uses RS-2026.1 at 2026-04-01T00:00:00Z, normalises every creation timestamp to UTC and treats an age equal to its window as not yet past-window. For holds with more than one placement or release, the latest event effective by that instant governs.

| category | past window | eligible after active holds |
|---|---:|---:|
| txn_log | 58 | 53 |
| support_corr | 31 | 28 |
| marketing_contact | 24 | 20 |
| audit_trail | 0 | 0 |
| hr_applicant | 19 | 17 |
| session_replay | 37 | 31 |
| total | 169 | 149 |

Active holds remove 20 overdue records from consideration. In descending identifier order they are REC-00383, REC-00353, REC-00297, REC-00293, REC-00289, REC-00263, REC-00220, REC-00195, REC-00164, REC-00158, REC-00144, REC-00127, REC-00122, REC-00116, REC-00087, REC-00067, REC-00065, REC-00041, REC-00017 and REC-00004. The resulting destruction population is 149.

Converting to UTC flips fourteen near-cutoff classifications. Positive offsets put REC-00362, REC-00352, REC-00288, REC-00183 and REC-00024 beyond their limits, making them destroyable. Negative offsets leave REC-00363, REC-00338, REC-00241, REC-00228, REC-00176, REC-00133, REC-00035, REC-00032 and REC-00026 short of their limits, so they are retained. The return also points to REC-00277 and REC-00165. Both land exactly on the cutoff, so neither is past-window and both remain off the destruction list. The operative schedule says the age must exceed—not merely equal—the window. Removing them turns the rejected 171 / 151 into 169 / 149.

The April run selected 153 distinct candidates. Its receipt table is an append-only journal with 157 events, including three replay events, two provisional receipts later voided and reissued, and four failed attempts that later succeeded. Resolving those event histories produces 146 unique valid final deletion receipts, not 157 deletions.

The no-receipt skip cohort, written in reverse identifier order, is REC-00108, REC-00046, REC-00040, REC-00028, REC-00013, REC-00012 and REC-00005. These seven candidates were skipped as object_locked and had no valid final receipt. By contrast, the timeouts for REC-00064, REC-00063, REC-00027 and REC-00019 are not misses: later attempts for all four ended in surviving receipts.

Run evidence identifies deployment DPL-20260401-017. Its Git deployment record resolves that identifier to RS-2026.1, selector-v2.4.0 and lock-adapter-v1.8.1.

The selector history explains the first departure. Selector-v2.3.1 converted the complete supplied datetime into UTC. The production revision, v2.4.0, slices out the local date-time portion and attaches UTC directly, so the original zone displacement is lost.

The upstream pin supplies the missing storage contract. Qumulo/filelock keeps `recent_locks` briefly to suppress repeat notification-driven lock processing: it compares each entry's age with its cooldown, whose default is five seconds. It is not a durable statement about whether an object is locked. Internal history shows v1.8.1 answering “locked” from cache presence alone without comparing entry age or expiry. V1.8.2 rejects entries older than the caller-provided limit. Production used v1.8.1. Its seven skipped records had already-released holds, but stale cache observations were mistaken for current state.

The run-level disposition confirms both defects:

| cohort | actual treatment |
|---|---|
| nine records whose negative offsets keep them inside-window | each has a surviving deletion receipt |
| five destroyable records with positive offsets | none appears among the candidates |
| seven records with released holds | each was selected, skipped and left without a surviving receipt |

The final exposure is internally consistent: 146 receipts comprise 137 correct deletions and 9 ineligible deletions. Twelve eligible records remain, comprising the five selector omissions and seven adapter skips. Therefore 9 ineligible records were destroyed, 12 eligible records were missed and 21 records received divergent treatment overall.
EOF
