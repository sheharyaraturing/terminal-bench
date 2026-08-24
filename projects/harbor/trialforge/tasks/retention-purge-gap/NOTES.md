# NOTES — retention-purge-gap v7

## Premise and dependency chain

The prompt and original 400-record compliance problem are unchanged. V7 preserves the complete v6 evidence architecture and changes only the verifier contract:

1. reconcile the in-force schedule, 400 records and effective hold histories;
2. derive the defensible destruction list;
3. resolve deployment `DPL-20260401-017` through Git;
4. reconstruct final deletions from an append-only receipt journal;
5. map the discrepancies through purge logs, internal diffs and pinned upstream behavior.

The runtime deliberately separates surfaces: filesystem exposes only `/data/purge`, SQLite serves the record and run data, and Git alone exposes `/opt/retention-platform`. The purge run carries `evidence_source_id = EVSRC-RETENTION-PLATFORM`; its foreign-key row identifies `source_type = version_control_repository` and resolves to that Git-only path.

## Deterministic evidence

`environment/fixtures/build_fixture.sh` reproducibly creates:

| evidence | rows/events |
|---|---:|
| retention records | 400 |
| hold events | 67 |
| purge candidates | 153 |
| append-only receipt events | 157 |
| unique valid final receipts | 146 |

The hold ledger includes six multi-cycle histories. At the assessment instant, 36 holds are active and 20 of those records are past-window. A simplistic “any release means inactive” interpretation misclassifies four active records.

The receipt journal includes four failed attempts followed by success, two issued-then-voided receipts, two replacement issues and three replay events. Resolving event state—not counting rows—produces 146 unique final deletions. Six bounded logs expose only the run and deployment identifiers, seven skip events, four resolved retries and the void/reissue activity.

`verify_fixture.py` independently reopens the SQL, logs and completed bundle before writing `GROUND_TRUTH.md`. Authoring builders, source CSV, overlays and ground truth are not copied into the runtime.

## Git provenance and causal upstream

The synthetic internal fork imports the audited `qfs_filelock.py` source and MIT license from Qumulo/filelock commit `debde74347f4147d0d2c745b1e4d98c1c64dfa74`. Only the pinned source establishes that `recent_locks` is a five-second age-checked duplicate-notification debounce; neither runtime logs nor internal documentation explains that contract.

The deployment ID resolves through `deploy/production.toml` to RS-2026.1, `selector-v2.4.0`, `lock-adapter-v1.8.1` and the pinned upstream contract. Git comparisons establish:

- selector v2.3.1 preserved offsets; deployed v2.4.0 discarded them;
- adapter v1.8.1 treated cache membership as durable lock state; v1.8.2 restored expiry-aware behavior.

The repository lives at `/opt/retention-platform`. It is outside the filesystem MCP root and available only through Git tools. The imported upstream snapshot excludes unrelated historical demo credentials while preserving the exact causal source, license and verified hashes.

## Ground truth and reward contract

The policy truth remains 169 past-window, 20 actively held and 149 eligible:

| category | past | eligible |
|---|---:|---:|
| txn_log | 58 | 53 |
| support_corr | 31 | 28 |
| marketing_contact | 24 | 20 |
| audit_trail | 0 | 0 |
| hr_applicant | 19 | 17 |
| session_replay | 37 | 31 |

The selector defect yields nine wrongful deletions and five eligible misses. The adapter defect adds seven eligible misses. Final exposure is 9 ineligible records destroyed, 12 eligible records missed and 21 divergent treatments.

The 29 equal-credit claims are deliberately short and atomic. The count is an outcome of the split, not a cap:

- six per-category reconciliation claims, each limited to that category's two requested figures;
- two ten-record active-hold ID sets that accept one clearly labelled combined 20-record list, plus one separate governing-ground claim;
- two offset-sensitive cohorts and two exact-boundary claims;
- separate candidate, receipt, object-lock ID and object-lock treatment claims;
- two deployment claims, two selector claims, two pinned-upstream claims and three adapter claims;
- two actual-treatment mappings and one separately derived final under-destruction total.

Each claim contains one requested reconciliation, classification set, treatment, mapping or causal predicate. A per-category `past / eligible` pair is one reconciliation; a cohort is one set-valued output; and the two directly related treatment facts in the object-lock claim have explicit partial credit. Splitting those further would disproportionately weight the easiest tabulation and ID-list work. The pinned-upstream purpose and age-rule claims remain separate because one establishes what the cache represents and the other establishes how its short-lived contract is enforced. The former final over-destruction criterion was removed because the negative-offset receipt-mapping claim already establishes the same nine wrongful deletions. The final under-destruction total remains distinct because it reconciles two separate miss cohorts: five selector omissions plus seven adapter skips. A manual replay against the six v6 substantive answers still projects two passes at approximately 0.83 and 0.76, with four differentiated failures at approximately 0.72, 0.72, 0.69 and 0.66. The exact five-second value remains optional supporting detail.

## Tool surface and difficulty

The task exposes exactly 24 tools across nine MCP servers, with no shell, code executor, process launcher, installer, filesystem multi-read or Git mutation tool. The intended path now requires evidence from SQLite, filesystem logs and four distinct Git findings. The planning target is 58 calls; a complete trajectory is expected around 45–65 calls and roughly 6.5 human hours. Hosted results, rather than these estimates, determine promotion.

## Hosted Oracle diagnosis — job bd0a60e2

The first hosted run of the 29-claim verifier returned `0.931` because criteria 7 and 8 each received zero. The hosted final answer, hosted Oracle artifact and local `solve.sh` answer were byte-identical at SHA-256 `9bcb0608a0836548bd2bdea2b75f2937066770d968a65e024d507f89e6a3d79e`; the answer correctly labelled and listed the complete 20-record past-window active-hold set. The old criterion wording nevertheless treated the other correct ten records as an impermissible superset because the authoring-only A/B split was not repeated in the answer.

The correction changes only those two descriptions. A combined, clearly labelled list of the required 20 now satisfies both halves, while an unfiltered list of all 36 active holds still earns zero. The Oracle answer, prompt, fixture, tool surface and claim count are unchanged. The next checksum-matched hosted Oracle must still return `1.00` before model runs.

## Local v7 verifier verification — 2026-08-23

The fixture hashes and MCP smoke results below carry forward from v6. This verifier-only edit did not rebuild or alter the environment.

- Two full regenerations produced byte-identical SQL, six logs, internal Git history and ground truth.
- `retention.sql` SHA-256: `627f1830b0ea400603c3600893788d507693d2b4f9005dd50aa4c6478ee2532d`.
- `retention-platform.bundle` SHA-256: `9eb1c610538f39d0bf81a080d39628640987ca4dcb07bebd81522f07ea31ce1d`.
- `GROUND_TRUTH.md` SHA-256: `a14bb808693f7c50609a0e5ef457a28dc8680cc3b4dd219314f09b29ca5896dd`.
- Production tag: `e96a3723493b1c12b8dc9c690e25ffaa59a67f75`; audit head: `142df28742e16324dc650d3956c9d175a5bf52aa`.
- The arm64 task image built successfully. Exact MCP smoke checks proved filesystem reads of `/opt/retention-platform` are denied while Git log, show and diff work there.
- No paid model call, upload, push, PR action or tracker promotion is part of local generation or QC.

## Promotion state

All v1–v6 jobs and existing QC workbooks are historical evidence only for v7. V7 remains **In progress** pending upload, Oracle 1.00, reviewed model results and claim-by-claim judge-fairness QC. Because only the verifier changed, v6 final answers may be regraded when the platform exposes that action. The model pass threshold is reward at least 0.75; infrastructure incidents are replaced rather than counted.
