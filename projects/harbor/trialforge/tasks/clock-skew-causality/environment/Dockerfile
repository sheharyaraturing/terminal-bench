FROM us-central1-docker.pkg.dev/turing-delivery-rl-gym/daytona/turing-mcpatlas:0.0.3

# Required: clear the image's sandbox entrypoint so it does not compete with
# Harbor's own agent process.
ENTRYPOINT []
CMD ["/bin/bash"]

# ── Fixtures ────────────────────────────────────────────────────────────────
# task.toml carries NO docker_image key on purpose: with one, harbor pulls a
# prebuilt image, skips this file, and none of the fixture below exists.

# Three services' records of one window, each rotated into four slices,
# `<svc>.log` newest. No single file holds the answer.
COPY fixtures/logs/ /data/logs/

# The size band is load-bearing: every slice UNDER tool_output_cap = 60000 so it
# reads whole, every rotation far OVER it so no service does. See NOTES.md.
RUN set -eu; \
    test "$(ls /data/logs | wc -l)" = "12"; \
    for f in /data/logs/*; do \
      test "$(wc -c < "$f")" -lt 60000 || { echo "slice over cap: $f"; exit 1; }; \
    done; \
    for svc in api worker db; do \
      test "$(cat /data/logs/$svc.log* | wc -c)" -gt 150000 \
        || { echo "$svc rotation too small to force a scripted read"; exit 1; }; \
    done; \
    test "$(cat /data/logs/api.log.3 /data/logs/api.log.2 /data/logs/api.log.1 /data/logs/api.log | wc -l)" = "1701"; \
    test "$(cat /data/logs/worker.log.3 /data/logs/worker.log.2 /data/logs/worker.log.1 /data/logs/worker.log | wc -l)" = "1735"; \
    test "$(cat /data/logs/db.log.3 /data/logs/db.log.2 /data/logs/db.log.1 /data/logs/db.log | wc -l)" = "1490"; \
    test "$(cat /data/logs/api.log* | grep -c 'status=502')" = "23"; \
    test "$(cat /data/logs/db.log* | grep -c 'msg=pool_exhausted')" = "31"; \
    test "$(cat /data/logs/worker.log* | grep -c 'requeued=true')" = "1"; \
    cat /data/logs/api.log* | grep -q '^2024-11-14T09:30:12\.000Z ERROR api .*status=502'; \
    cat /data/logs/db.log*  | grep -q '^2024-11-14T09:31:00\.000Z ERROR db .*msg=pool_exhausted'
