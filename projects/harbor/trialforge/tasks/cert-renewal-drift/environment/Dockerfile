FROM us-central1-docker.pkg.dev/turing-delivery-rl-gym/daytona/turing-mcpatlas:0.0.3

# Required: clear the image's sandbox entrypoint so it does not compete with
# Harbor's own agent process.
ENTRYPOINT []
CMD ["/bin/bash"]

# ── Fixtures ────────────────────────────────────────────────────────────────
# task.toml carries NO docker_image key on purpose: with one, harbor pulls a
# prebuilt image, skips this file, and none of the fixture below exists.

# A 240-host certificate inventory exported in 8 batches, `inventory.csv`
# last, plus the renewal ticket log, the decommission register, the rotation
# log and the scope note.
COPY fixtures/certs/ /data/certs/

# The size band is load-bearing: every file UNDER tool_output_cap = 60000 so it
# reads whole, the inventory far OVER it so no read gets the fleet. See NOTES.md.
RUN set -eu; \
    C=/data/certs; T=$C/renewal_tickets.csv; \
    test "$(ls $C | wc -l)" = "12"; \
    for f in $C/*; do \
      test "$(wc -c < "$f")" -lt 60000 || { echo "over cap: $f"; exit 1; }; \
    done; \
    test "$(cat $C/inventory.csv* | wc -c)" -gt 150000 \
      || { echo "inventory too small to force a scripted join"; exit 1; }; \
    test "$(cat $C/inventory.csv* | grep -c '^hostname,')" = "8"; \
    test "$(cat $C/inventory.csv* | wc -l)" = "251"; \
    test "$(cat $C/inventory.csv* | grep -c ',decommissioned,')" = "3"; \
    test "$(wc -l < $T)" = "71"; \
    test "$(grep -c ',closed,' $T)" = "58"; \
    test "$(grep -c ',open,' $T)" = "12"; \
    test "$(grep -c ',requester_attested,' $T)" = "16"; \
    test "$(grep -c ',rescan_verified,' $T)" = "42"; \
    cut -d, -f8 $T | tail -n +2 | grep -v '^$' | sort -u > /tmp/tgt; \
    test "$(cat $C/inventory.csv* | grep -F -f /tmp/tgt | wc -l)" = "45"; \
    cut -d, -f7 $T | tail -n +2 | grep -v '^$' | sort -u > /tmp/rep; \
    test "$(cat $C/inventory.csv* | grep -F -f /tmp/rep | wc -l)" = "23"; \
    rm -f /tmp/tgt /tmp/rep; \
    test "$(wc -l < $C/rotation_log.csv)" = "15"; \
    test "$(grep -c ',scheduled$' $C/decommissions.csv)" = "1"; \
    grep -q '^notify-worker-02\.dr\.hbl\.example\.com,2026-09-30,.*,scheduled$' $C/decommissions.csv; \
    cat $C/inventory.csv* | grep -qE '^notify-worker-02\.dr\.hbl\.example\.com,.*,2026-08-09T13:22:05Z,.*,active,'; \
    cat $C/inventory.csv* | grep -qE '^identity-idp-01\.prod\.hbl\.example\.com,.*,2027-07-23T09:11:00Z,.*,active,'; \
    grep -qE ',identity-idp-01\.prod\.hbl\.example\.com,.*,closed,[0-9A-F]{32},[0-9A-F]{32},.*,requester_attested,' $T; \
    grep -q 'assessment_as_of = 2026-08-17T00:00:00Z' $C/audit_scope.md; \
    grep -q 'expiry_window_days = 30' $C/audit_scope.md; \
    grep -q 'expiry_window_ends = 2026-09-16T00:00:00Z' $C/audit_scope.md; \
    cat $C/inventory.csv* | grep -qE '^media-cdn-02\.prod\.hbl\.example\.com,.*,2026-06-24T10:05:44Z,.*,decommissioned,'; \
    grep -q '^media-cdn-02\.prod\.hbl\.example\.com,2026-06-30,' $C/decommissions.csv; \
    test "$(cut -d, -f3 $T | grep -c '^media-cdn-02\.prod\.hbl\.example\.com$')" = "0"; \
    cat $C/inventory.csv* | grep -qE '^admin-console-04\.dr\.hbl\.example\.com,.*,2026-11-03T05:14:22Z,'; \
    for t in \
      "admin-console-03.prod|352112C989A614BCB0D0A2A8B40E5F10|2026-07-28T11:42:07Z" \
      "catalog-api-01.dr|070BF26F4AD160F2CE300ACB409AF511|2026-08-21T04:36:02Z" \
      "fraud-scorer-01.prod|A3782771A64AB5EF2C2EDFA459474A83|2026-08-02T06:19:51Z" \
      "identity-idp-04.prod|26F6C7C7106F23294938F7F0CAB70A47|2026-08-06T15:03:28Z" \
      "notify-worker-01.stage|A9D3FA25F8E846704646BC2921D0269B|2026-08-11T09:27:14Z" \
      "partner-gw-04.prod|16459D182319F68371EDCE4D559D812B|2026-08-29T13:48:45Z" \
      "search-api-01.corp|193FDAA3192D7CCF37E6B0D42A38B926|2026-08-14T20:55:39Z" \
      "status-page-03.prod|FCE4D4CF9DC97FDC825C5A1F91EBBFA2|2026-09-04T07:11:30Z" \
      "webhook-relay-03.corp|14BE6CE916F3B0B4B271F5EABF405E4A|2026-09-11T18:24:09Z" \
    ; do \
      h=${t%%|*}; r=${t#*|}; s=${r%%|*}; n=${r##*|}; \
      cat $C/inventory.csv* | grep -qE "^$h\.hbl\.example\.com,.*,$s,[^,]*,$n," \
        || { echo "drift record missing or altered: $h"; exit 1; }; \
      grep -qE ",$h\.hbl\.example\.com,.*,closed,$s,[0-9A-F]{32},.*,requester_attested," $T \
        || { echo "attested ticket missing or altered: $h"; exit 1; }; \
    done
