#!/bin/bash
set -euo pipefail

# Oracle acceptance answer. Write both paths because separate-mode verification
# grades the collected artifact rather than the shared agent directory.
mkdir -p /logs/agent /logs/artifacts

tee /logs/agent/final_answer.txt /logs/artifacts/final_answer.txt <<'EOF'
Flag review memo for the 2026-08-21 18:00 UTC cutoff

Authority and scope

The current authority is production snapshot `prod-2026.08.21.4`, which names
application build `app-2026.08.21.4` and the live stable and canary cohorts. The
July flag-layer migration note is not evidence of current behaviour: it is a
pending, unapproved draft for `prod-2026.09.1`. The release-matched flag README,
the production snapshot and the loader agree on the rule in force now.

The adjacent read-only resolver export carries the same release, application
build, configuration bundle and cutoff as the snapshot. Its values and winning
layers reproduce the default-to-staging-to-production merge plus the named
canary override, so it is consistent corroborating evidence rather than a
different source of truth.

The application build manifest limits production source to `platform/`,
`services/` and `web/src/`. Tests, docs and examples are not shipped and cannot
establish production liveness.

Resolution and rollout

The loader applies `default.json`, then `staging.json`, then `prod.json`; later
definitions win and staging participates in production. It then applies only
the runtime override IDs named for the request cohort in the current snapshot.
An expired override or an override for another release is not active.

All 21 configured canonical gates resolve in each cohort:

| Cohort | Traffic | default | staging | prod | runtime |
|---|---:|---:|---:|---:|---:|
| stable | 80% | 2 | 6 | 13 | 0 |
| canary | 20% | 2 | 5 | 13 | 1 |

Prod is silent on six stable values, so staging supplies
`payments.dual_write_ledger`, `search.typo_tolerance`,
`billing.proration_v3`, `reporting.async_export`, `checkout.express_lane` and
`identity.passkey_enrolment`. The canary list drops the dual-write gate because
active override
`ovr-canary-ledger-20260821` supplies that gate instead.

Requirement finding

`payments.dual_write_ledger` is required by shipping source to be false in
production. Stable receives staging's true value, while canary receives false
from its active runtime override. The violation therefore affects the stable
80% of traffic, not the canary 20%.

This is the only violating canonical gate among the four shipping-source
requirements. `search.typo_tolerance=false`,
`reporting.warehouse_direct_read=true` and `identity.mfa_grace_hours=0` satisfy
their requirements in both cohorts. Only the stable cohort violates the
dual-write requirement.

Configured but unused by the shipped application

`billing.legacy_invoice_pdf` is the only configured canonical gate with no
reference from the manifest-defined shipping source set. Its layer values are
default false, staging true and prod false. The name does occur in a unit test
and the historical migration note, but both locations are outside the shipping
roots. Comparing all 21 configured canonical names against all alias-normalized
references in the three shipping roots leaves this one gate and no other.

Alias handling matters to that proof. Shipping source stores
`reporting.background_export` in `FLAG_ASYNC_EXPORT`, and the exporter passes
that constant to the accessor. `gate_registry.json` canonicalizes the alias to
`reporting.async_export`, which is configured and live. A literal or
canonical-name-only search would misclassify it.

Read by shipping source but not defined

`search.semantic_rerank` is the only canonical gate read by shipping source but
absent from every default, staging, prod and active runtime definition. This is
the result of an exhaustive alias-normalized comparison, not merely a search of
`prod.json`.

The undefined lookup uses each caller's fallback. The server-side ranker passes
false; the browser results panel passes true. It consequently has no single
resolved production value and behaves differently at the two call sites.

Cleanup taxonomy

1. Changes neither value nor behaviour:
   `notifications.digest_window_minutes` is live, but default, staging and prod
   are all 30. Removing the later entries still resolves to 30.

2. Changes the resolved table but not shipping behaviour:
   removing the prod entry for dead `billing.legacy_invoice_pdf` exposes
   staging true instead of false, but no shipped code reads it.

3. Changes both value and live behaviour:
   `identity.session_pinning` and `notifications.push_quiet_hours` are true in
   default, false in staging and true again in production. Removing either
   production entry exposes false to running code.

   `platform.request_shadowing` and `web.new_nav` are false in default, true in
   staging and false again in production. Removing either production entry
   exposes true to running code.

The operational priorities are therefore the 80%-exposed dual-write violation
and the inconsistent undefined rerank fallbacks. The billing PDF entries are
dead cleanup, the digest entries are value-neutral cleanup, and the four
baseline-restoring prod entries must not be treated as redundant.
EOF
