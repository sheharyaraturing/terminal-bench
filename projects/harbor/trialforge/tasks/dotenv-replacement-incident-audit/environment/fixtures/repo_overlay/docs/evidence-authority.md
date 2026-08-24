# Incident evidence authority

For the `2026-08-17T18:00:00Z` review, use the image digest in the cutoff
`deployment_assignments` snapshot and resolve it through
`deploy/image-manifest.toml`. A receipt's `worker_release_label` is descriptive
worker metadata and may lag an image change; it cannot override the recorded
digest.

`attempt_registry` and the worker logs describe attempts. The terminal receipts
and `receipt_index` are keyed by logical operation. A retried operation can
therefore have several attempts but exactly one terminal receipt. Compare the
preflight observation for that operation with its terminal receipt to determine
whether a workspace's source, target, link referent, or permissions changed.
