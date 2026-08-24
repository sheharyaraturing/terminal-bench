# Retention platform additions

This fork contains the retention selector, storage-lock adapter, schedules, regulator correspondence and production deployment record. Runtime evidence records a deployment identifier rather than component versions. Resolve that identifier through `deploy/production.toml`; the newest source file or policy document is not necessarily the deployed one.

## Purge stages

Candidate planning receives the governance service's effective hold set at the assessment instant and excludes those record IDs before selection. A storage worker then performs a defence-in-depth lock check immediately before deletion. A record can therefore be absent from the candidate set because its governance hold is active, or appear as a candidate and still be skipped by the storage check.

The receipt journal is append-only. `receipt_issued` creates a receipt, a later `receipt_voided` event cancels that receipt identifier, and `receipt_replayed` repeats journal delivery without creating another deletion. An `attempt_failed` event has no receipt. Final deletion evidence is therefore the set of distinct records attached to issued receipt identifiers that were never subsequently voided.
