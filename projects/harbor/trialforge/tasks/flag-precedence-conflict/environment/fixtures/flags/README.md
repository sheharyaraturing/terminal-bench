# Production flag configuration

This is the loader contract for release `prod-2026.08.21.4`, the release named
in `/data/deploy/production-snapshot.json`.

Three JSON layers live in this directory. A process loads them in the order
below, and each layer overrides the keys of the one before it:

    1. default.json    the baseline, loaded in every environment
    2. staging.json    loaded in staging AND in production
    3. prod.json       loaded in production only

`staging.json` is not a staging-only file. It was introduced as the shared
pre-production overlay back when we promoted one artefact from staging into
production, and the production loader has read it ever since. The filename is
historical and we have never renamed it. Development processes load
`default.json` on its own.

For production, the loader then reads the active override IDs listed for the
request's cohort in the production snapshot and applies their values last.
Entries in `runtime-overrides.json` that the snapshot does not name are not
active for this release, regardless of what value they contain.

A key that is absent from every active layer or override is not a load error.
The accessors in `app/platform/flags.py` and `app/web/src/shared/flags.ts` each
take a fallback argument and return it when the key cannot be resolved, so an
unknown key silently takes whatever value the call site passes.

Before lookup, the loader canonicalizes names through
`/data/app/platform/gate_registry.json`. Configuration uses canonical names;
shipping source may use a registered alias.

Values are plain JSON scalars — booleans for on/off gates, integers for
budgets, windows, sizes and timeouts.

Ownership lives in the service directories rather than here. Where a flag is
required to resolve to a particular value in production, the requirement is
recorded as a comment line beginning `PROD-REQUIREMENT:` next to the accessor
call. Those comment lines are the contract our platform review is held to.
