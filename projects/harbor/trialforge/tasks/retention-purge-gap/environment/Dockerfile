FROM us-central1-docker.pkg.dev/turing-delivery-rl-gym/daytona/turing-mcpatlas:0.0.3

# Harbor supplies the agent process. The base sandbox entrypoint must not compete.
ENTRYPOINT []
CMD ["/bin/bash"]

# Add the retention evidence to the base warehouse. Authoring inputs and
# GROUND_TRUTH.md are intentionally not copied into the runtime.
COPY fixtures/retention.sql /tmp/retention.sql
RUN sqlite3 /data/db/turing.db < /tmp/retention.sql \
 && rm /tmp/retention.sql

# Only the completed internal bundle is materialised. It contains the pinned,
# sanitized upstream source and MIT license plus the synthetic internal release
# and deployment history under one repository.
COPY fixtures/bundles/retention-platform.bundle /tmp/retention-platform.bundle
RUN git clone -q /tmp/retention-platform.bundle /opt/retention-platform \
 && git -C /opt/retention-platform checkout -q audit-review \
 && git config --system --add safe.directory /opt/retention-platform \
 && rm /tmp/retention-platform.bundle

COPY fixtures/logs/ /data/purge/run-20260401/

# Fail the image build if any phase-defining property drifted.
RUN test "$(sqlite3 /data/db/turing.db 'SELECT COUNT(*) FROM retention_records')" = "400" \
 && test "$(sqlite3 /data/db/turing.db 'SELECT COUNT(*) FROM retention_hold_events')" = "67" \
 && test "$(sqlite3 /data/db/turing.db 'SELECT r.run_id || char(124) || s.source_id || char(124) || s.source_type || char(124) || s.repository_path FROM purge_runs r JOIN purge_evidence_sources s ON s.source_id = r.evidence_source_id')" = "PURGE-2026-04-01-A|EVSRC-RETENTION-PLATFORM|version_control_repository|/opt/retention-platform" \
 && test "$(sqlite3 /data/db/turing.db 'SELECT COUNT(*) FROM purge_candidates')" = "153" \
 && test "$(sqlite3 /data/db/turing.db 'SELECT COUNT(*) FROM purge_receipts')" = "157" \
 && test "$(sqlite3 /data/db/turing.db 'SELECT COUNT(DISTINCT record_id) FROM purge_receipts WHERE event_type = "receipt_issued" AND receipt_id NOT IN (SELECT receipt_id FROM purge_receipts WHERE event_type = "receipt_voided")')" = "146" \
 && test "$(sqlite3 /data/db/turing.db '.schema retention_records' | grep -c legal_hold)" = "0" \
 && test "$(find /data/purge/run-20260401 -type f -name 'purge-worker-*.log' | wc -l)" = "6" \
 && test "$(grep -h -c 'result=skipped code=object_locked' /data/purge/run-20260401/*.log | awk '{s+=$1} END {print s}')" = "7" \
 && test "$(grep -h -c 'result=failed code=storage_timeout' /data/purge/run-20260401/*.log | awk '{s+=$1} END {print s}')" = "4" \
 && test "$(grep -h -c 'result=receipt_voided code=confirmation_timeout' /data/purge/run-20260401/*.log | awk '{s+=$1} END {print s}')" = "2" \
 && test "$(grep -h -c 'deployment_id=DPL-20260401-017' /data/purge/run-20260401/*.log | awk '{s+=$1} END {print s}')" = "6" \
 && ! grep -Eh 'selector-v|lock-adapter|RS-2026|qfs_recent|cache_age_seconds|evidence_repo' /data/purge/run-20260401/*.log \
 && test ! -e /data/repos/retention-platform \
 && git -C /opt/retention-platform cat-file -e upstream-qumulo-filelock-debde743^{commit} \
 && test "$(git -C /opt/retention-platform rev-parse refs/remotes/origin/production)" = "$(git -C /opt/retention-platform rev-parse prod-2026-04-01)" \
 && test "$(git -C /opt/retention-platform show audit-review:reports/2026-Q1-regulator-return.md | grep -c 'two inventory records')" = "1" \
 && test "$(git -C /opt/retention-platform show upstream-qumulo-filelock-debde743:qfs_filelock.py | grep -c 'current_time - recent_locks\[full_path\].*< cooldown')" = "1" \
 && test "$(git -C /opt/retention-platform show upstream-qumulo-filelock-debde743:UPSTREAM_PROVENANCE.md | grep -c 'debde74347f4147d0d2c745b1e4d98c1c64dfa74')" = "1" \
 && test "$(git -C /opt/retention-platform show lock-adapter-v1.8.1:platform_retention/hold_adapter.py | grep -c 'return storage_path in recent_locks')" = "1" \
 && test -s /opt/retention-platform/LICENSE \
 && test ! -e /opt/retention-platform/qfs_filelock_config.ini \
 && test ! -e /opt/retention-platform/test_qfs_filelock.sh \
 && test -s /opt/retention-platform/deploy/production.toml
