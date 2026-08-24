# GROUND_TRUTH.md - flag-precedence-conflict V3

Derived independently from the emitted agent-facing files by `audit_fixture.py`.
The builder's in-memory tables are not imported.

## Authority and shipping scope

- snapshot: `prod-2026.08.21.4` at `2026-08-21T18:00:00Z`
- shipping roots: `platform`, `services`, `web/src`
- excluded roots: `tests`, `docs`, `examples`
- shipping files: **79**
- agent-facing tree SHA-256: `c4decd716383331dc159c743bca228e248cb1ce518654a943b753b3f03450480`
- current README matches the snapshot release; the migration note is pending and targets another release
- the read-only resolver export matches an independent layer-and-override derivation

## Cohort resolution

- **stable (80%)**: default.json 2, prod.json 13, staging.json 6
  - staging winners: billing.proration_v3, checkout.express_lane, identity.passkey_enrolment, payments.dual_write_ledger, reporting.async_export, search.typo_tolerance
- **canary (20%)**: default.json 2, prod.json 13, runtime:ovr-canary-ledger-20260821 1, staging.json 5
  - staging winners: billing.proration_v3, checkout.express_lane, identity.passkey_enrolment, reporting.async_export, search.typo_tolerance

## Requirements

- documented shipping-source requirements: **4**
- violating canonical gates: **1**: `payments.dual_write_ledger`
- `payments.dual_write_ledger` is stable `true`, canary `false`; violation exposure **80%**

## Shipping liveness

- dead configured canonical gates: `billing.legacy_invoice_pdf`
- undefined canonical gates read by shipping code: `search.semantic_rerank`
- alias: `reporting.background_export` -> `reporting.async_export`; the canonical gate is live
- `billing.legacy_invoice_pdf` occurs only outside the manifest's shipping roots

### Undefined fallback evidence

- `app/services/search/ranker.py`: `if flags.get_bool("search.semantic_rerank", default=False):`
- `app/web/src/search/resultsPanel.ts`: `const reranked = isEnabled("search.semantic_rerank", true);`

## Cleanup taxonomy

- `notifications.digest_window_minutes`: removing staging and prod changes neither the resolved value nor behaviour
- `billing.legacy_invoice_pdf`: removing prod changes the resolved value from false to true, but no shipping behaviour
- live baseline-restoring prod entries whose removal changes both value and behaviour:
  - `identity.session_pinning`
  - `notifications.push_quiet_hours`
  - `platform.request_shadowing`
  - `web.new_nav`
