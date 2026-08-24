# Author notes: flag-precedence-conflict V3

These notes are author-only and must not be copied into `/data`.

## Why V2 existed

Three GLM-5.3 V1 trials produced rewards 0.9643, 1.0000 and 0.8929 with
68, 78 and 70 tool calls. Under the meeting's provisional 0.75 pass boundary,
that was 3/3 passing rather than a breaking task. Two failed UI statuses also
rested on judge defects: the uniqueness claims prescribed one proof shape and
the cleanup wording conflated resolved-value changes with live behaviour.

V2 repairs those claims and adds dependent, production-realistic complexity:

1. a fixed production snapshot with stable and canary cohorts;
2. a snapshot-selected runtime override;
3. a manifest-defined shipping source boundary;
4. a canonical alias registry used by the loader;
5. a dated, unapproved migration draft for another release;
6. separate value-change and behaviour-change cleanup categories.

No random CSVs, filler servers or unrelated documents were added. The model had
already handled broad filesystem noise cheaply. Each new artifact changes a
real conclusion and remains visibly resolvable.

## V3 calibration

V2 produced valid partial GLM-5.3 rewards of 0.500, 0.633 and 0.567 at 22, 16
and 31 calls. Kimi K3 produced 0.900, 0.967 and 0.967 at 57, 32 and 33 calls.
V3 therefore sets `target_tool_calls = 32`, the six-run mean rounded from 31.8.

The fixture now includes `deploy/effective-flag-report.json`, a release-matched,
read-only resolver export containing only cohort values and winning layers. The
independent audit recomputes and verifies the export. It does not disclose
requirements, violations, liveness, alias meaning, fallbacks or cleanup
classification, so those findings still require source investigation.

The prompt now defines exposure as the production traffic receiving a
noncompliant resolved value. The former four-gate cleanup claim is split into
two value-shaped pairs for fairer partial credit.

## Hosted V3 evidence

- Platform task: `tf_003` V3; Oracle passed at `1.00`.
- GLM-5.3 job: `fce9473e-b31c-4aa0-bcf2-1ebfcd589b60`.
- Rewards: `0.813`, `0.594`, `0.906`; mean `0.771`.
- Tool calls: `18`, `49`, `32`; mean `33`, consistent with the target of `32`.
- At the provisional `0.75` boundary this is `2/3` passing, within the requested
  `1-2/3` calibration band.

All three trajectories completed naturally. Trial 1 omitted the
`platform.request_shadowing` and `web.new_nav` cleanup pair. Trial 2 incorrectly
reversed layer values, rejected a correct resolver export and propagated the
mistake into counts and cleanup. Trial 3 missed the browser-side `true`
fallback for `search.semantic_rerank`. These are model reasoning or coverage
failures, not infrastructure failures.

The claim-level audit found two opposing judge inconsistencies in trial 2:
criterion 1 was too strict about calling the July-updated, September-targeted
document a "September draft", while criterion 8 awarded full credit despite
the answer reversing two layer values. Correcting both leaves the scalar score
unchanged at 0.594. Even a generous, principled regrade remains below 0.75, so
the GLM classification is robust despite those recorded judge deviations.

Hosted no-op remains unverified: the launcher exposes no no-op agent, and both
the active and commented local OpenRouter keys return HTTP 401. The task owner
explicitly deferred this unavailable control on 2026-08-22. Record it as
unverified rather than passed; it does not invalidate the hosted Oracle or GLM
evidence.

## Deterministic fixture contract

Run from `environment/fixtures`:

```bash
bash build_fixture.sh
python3 audit_fixture.py --check-only
```

The seeded builder emits only:

- `flags/`: 21 / 15 / 13 static layer keys plus runtime overrides;
- `deploy/production-snapshot.json`: fixed cutoff and 80/20 cohorts;
- `deploy/effective-flag-report.json`: read-only cohort resolution diagnostic;
- `app/`: 84 files, with 79 files under manifest shipping roots;
- `docs/flag-layer-migration-draft.md`: pending July draft for September;
- `GROUND_TRUTH.md` and `GROUND_TRUTH.json`: author-only read-back outputs.

`audit_fixture.py` imports no builder state. It independently reopens the
snapshot, layers, overrides, manifest, alias registry and shipping source. It
asserts cohort counts, requirement exposure, liveness uniqueness, fallbacks,
cleanup categories and provenance. Docker copies only `flags`, `deploy`, `app`
and `docs`, and asserts that builder, audit and ground-truth files are absent
from `/data`.

## Ground-truth summary

- Stable 80%: default 2, staging 6, prod 13.
- Canary 20%: default 2, staging 5, prod 13, runtime 1.
- `payments.dual_write_ledger` violates its false requirement only in stable,
  for 80% exposure.
- `billing.legacy_invoice_pdf` is the sole configured canonical gate absent
  from manifest shipping source; its test and historical hits are excluded.
- `reporting.background_export` canonicalizes to live
  `reporting.async_export` and is read through a constant.
- `search.semantic_rerank` is the sole shipping-read canonical gate absent from
  all active definitions; server fallback false, browser fallback true.
- Digest overrides change neither value nor behaviour; the dead billing prod
  entry changes value only; four live baseline-restoring prod entries change
  both value and behaviour.

## Reward and effort design

The rubric has 16 equally weighted three-point Likert claims. Uniqueness claims
accept an exhaustive comparison or any equivalent complete proof. Claims are
split across authority, precedence, cohort counts, rollout exposure, shipping
scope, alias handling, undefined fallbacks and cleanup impact. Missing the
snapshot or manifest affects several legitimate downstream claims while a
smaller alias miss affects fewer.

Across V2 GLM and Kimi runs, tool calls were 16, 22, 31, 32, 33 and 57. Metadata
uses `target_tool_calls = 32`, matching their rounded mean and median.

## Verification boundary

Local V3 checks must cover deterministic double-build, independent audit,
Docker leak assertions, static task QC and ZIP inspection. They do not replace:

- hosted Oracle = 1.00;
- hosted no-op <= 0.05;
- alternate-correct uniqueness answers = 1.00;
- stale-doc, test-only and alias-blind negative controls;
- GLM-5.3 x3 with trajectory and judge review;
- Kimi K3 x3 on the unchanged version if GLM failures are valid.

This V3 repair authorized hosted Oracle, no-op and GLM-5.3 x3 validation. Oracle
and GLM are complete; no-op is deferred as documented above. On 2026-08-22 the
task owner authorized PR preparation while Kimi K3 runs on the unchanged V3.
Keep the PR in draft and the tracker `In progress` until the remaining evidence
and final handoff are complete.
