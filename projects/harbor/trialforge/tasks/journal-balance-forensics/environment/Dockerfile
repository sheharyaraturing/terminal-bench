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
# Both artefacts are produced by fixtures/build_fixture.sh, which is
# deterministic (single seeded RNG) and whose read-back stage regenerates
# fixtures/GROUND_TRUTH.md from the emitted files.

# 1. The journal extract the task is about: 400 double-entry lines, one JSON
#    object per line, grouped into 140 entries. Lands inside /data, which is the
#    root the filesystem MCP server is given.
COPY fixtures/journal.jsonl /data/journal.jsonl

# 2. The period-close reference table. This is the second fixture the task needs:
#    the close date for each accounting period lives ONLY here, never in the
#    journal file, so the "posted after the books were shut" finding is not
#    derivable from /data/journal.jsonl alone.
#
#    extra.sql issues a single CREATE TABLE IF NOT EXISTS plus INSERTs. It does
#    not touch, alter or drop any of the eight tables already baked into
#    turing.db — those are shared with other tasks in the suite.
COPY fixtures/extra.sql /tmp/
RUN sqlite3 /data/db/turing.db < /tmp/extra.sql && rm /tmp/extra.sql

# Fail the build rather than ship a silently empty fixture.
RUN test -s /data/journal.jsonl \
 && test "$(wc -l < /data/journal.jsonl)" = "400" \
 && test "$(sqlite3 /data/db/turing.db 'SELECT COUNT(*) FROM gl_period_close;')" = "9" \
 && sqlite3 /data/db/turing.db 'SELECT COUNT(*) FROM sqlite_master WHERE type="table";'
