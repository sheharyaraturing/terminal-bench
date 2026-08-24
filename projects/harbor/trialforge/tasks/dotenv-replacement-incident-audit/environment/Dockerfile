FROM us-central1-docker.pkg.dev/turing-delivery-rl-gym/daytona/turing-mcpatlas:0.0.3

ENTRYPOINT []
CMD ["/bin/bash"]

# The bundles contain the pinned public upstream and a prominently fictional
# internal history. Clone them into separate read-only evidence repositories.
COPY fixtures/bundles/python-dotenv-upstream.bundle /tmp/python-dotenv-upstream.bundle
COPY fixtures/bundles/dotenv-replacement-internal.bundle /tmp/dotenv-replacement-internal.bundle

RUN mkdir -p /data/repos /data/incidents/dotenv-replacement \
 && git clone /tmp/python-dotenv-upstream.bundle /data/repos/python-dotenv-upstream \
 && git -C /data/repos/python-dotenv-upstream checkout --detach 751f8c148222e58aa173c83c4e5e6cfccb2cc124 \
 && git clone /tmp/dotenv-replacement-internal.bundle /data/repos/dotenv-replacement-internal \
 && git -C /data/repos/dotenv-replacement-internal checkout --detach prod-2026-08-17 \
 && rm /tmp/python-dotenv-upstream.bundle /tmp/dotenv-replacement-internal.bundle

COPY fixtures/incident.db /data/incidents/dotenv-replacement/incident.db
COPY fixtures/logs /data/incidents/dotenv-replacement/logs
COPY fixtures/receipts /data/incidents/dotenv-replacement/receipts
COPY fixtures/INCIDENT_README.md /data/incidents/dotenv-replacement/README.md

# Build-time boundary checks prevent author-only truth or generators from leaking
# into the runtime and pin the observable evidence cardinalities.
RUN test "$(git -C /data/repos/python-dotenv-upstream rev-parse HEAD)" = "751f8c148222e58aa173c83c4e5e6cfccb2cc124" \
 && test -s /data/repos/python-dotenv-upstream/LICENSE \
 && test -s /data/repos/dotenv-replacement-internal/INTERNAL_FORK_NOTICE.md \
 && test -s /data/repos/dotenv-replacement-internal/docs/replacement-contract.md \
 && test -s /data/repos/dotenv-replacement-internal/deploy/image-manifest.toml \
 && test "$(find /data/incidents/dotenv-replacement/logs -type f -name 'worker-*.log' | wc -l)" = "6" \
 && test "$(find /data/incidents/dotenv-replacement/receipts -type f -name 'receipt-*.jsonl' | wc -l)" = "6" \
 && test "$(wc -l < /data/incidents/dotenv-replacement/logs/worker-01.log)" = "30" \
 && test "$(wc -l < /data/incidents/dotenv-replacement/receipts/receipt-01.jsonl)" = "29" \
 && test ! -e /data/GROUND_TRUTH.md \
 && test ! -e /data/GROUND_TRUTH.json \
 && test ! -e /data/build_operational_fixture.py \
 && test ! -e /data/verify_fixture.py
