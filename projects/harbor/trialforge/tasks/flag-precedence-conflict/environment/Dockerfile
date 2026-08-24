FROM us-central1-docker.pkg.dev/turing-delivery-rl-gym/daytona/turing-mcpatlas:0.0.3

# Harbor supplies its own agent process. Clear the image's sandbox entrypoint so
# it does not compete. Required — do not remove.
ENTRYPOINT []
CMD ["/bin/bash"]

# ── Fixtures ──────────────────────────────────────────────────────────────────
# environment/ is the Docker build context, so everything under fixtures/ can be
# COPYd. This is a normal host build, not docker-in-docker.
#
# task.toml deliberately carries NO docker_image key: if it did, harbor would
# pull the prebuilt image and skip this file, and neither fixture below would
# exist at run time.
#
# All trees are produced by fixtures/build_fixture.sh. The separate
# fixtures/audit_fixture.py reads them back and creates author-only ground truth,
# which is deliberately not copied into the image.

# 1. The three configuration layers plus the README that states the order they
#    are applied in. The README is the only place the ordering rule is written
#    down, and it is what makes the production value of a key absent from
#    prod.json non-obvious. Lands inside /data, which is the root the filesystem
#    MCP server is given.
COPY fixtures/flags /data/flags

# 2. The application tree the layers configure, including its shipping manifest
#    and alias registry. Liveness is derived only from the manifest's production
#    source roots, so test-only references do not become production evidence.
COPY fixtures/app /data/app

# 3. The fixed production rollout snapshot and dated operational notes. The
#    snapshot is current for the review cutoff. The migration note is a pending
#    proposal for another release and must be assessed from its provenance.
COPY fixtures/deploy /data/deploy
COPY fixtures/docs /data/docs

# Fail the build rather than ship a silently empty or half-copied fixture. The
# final assertions pin the production source boundary and prevent author-only
# audit outputs from entering the agent environment.
RUN test -s /data/flags/default.json \
 && test -s /data/flags/staging.json \
 && test -s /data/flags/prod.json \
 && test -s /data/flags/runtime-overrides.json \
 && test -s /data/flags/README.md \
 && test -s /data/deploy/production-snapshot.json \
 && test -s /data/deploy/effective-flag-report.json \
 && test -s /data/docs/flag-layer-migration-draft.md \
 && test -s /data/app/build-manifest.json \
 && test -s /data/app/platform/gate_registry.json \
 && test "$(python3 -c 'import json;print(len(json.load(open("/data/flags/default.json"))))')" = "21" \
 && test "$(python3 -c 'import json;print(len(json.load(open("/data/flags/staging.json"))))')" = "15" \
 && test "$(python3 -c 'import json;print(len(json.load(open("/data/flags/prod.json"))))')" = "13" \
 && test "$(find /data/app -type f | wc -l)" = "84" \
 && test "$(find /data/app/platform /data/app/services /data/app/web/src -type f | wc -l)" = "79" \
 && test "$(grep -rl 'billing.legacy_invoice_pdf' /data/app/tests | wc -l)" = "1" \
 && test "$(grep -rl 'billing.legacy_invoice_pdf' /data/app/platform /data/app/services /data/app/web/src | wc -l)" = "0" \
 && test "$(grep -rl 'billing.legacy_invoice_pdf' /data/docs | wc -l)" = "1" \
 && test "$(grep -rl 'search.semantic_rerank' /data/app/platform /data/app/services /data/app/web/src | wc -l)" = "2" \
 && test "$(grep -rc 'PROD-REQUIREMENT:' -r /data/app/platform /data/app/services /data/app/web/src | grep -v ':0$' | wc -l)" = "4" \
 && test ! -e /data/GROUND_TRUTH.md \
 && test ! -e /data/GROUND_TRUTH.json \
 && test ! -e /data/audit_fixture.py \
 && test ! -e /data/build_fixture.sh
