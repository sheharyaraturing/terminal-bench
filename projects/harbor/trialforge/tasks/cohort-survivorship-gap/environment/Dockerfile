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
# pull the prebuilt image and skip this file, and the three tables below would
# not exist at run time.
#
# The artefact is produced by fixtures/build_fixture.sh, which is deterministic
# (one seeded RNG, and normal deviates built by hand so the output does not
# depend on the CPython gaussian implementation). Its read-back stage executes
# the SQL into a scratch database and regenerates fixtures/GROUND_TRUTH.md from
# SQL queries against that database.

# The whole fixture: three NEW warehouse tables.
#
#   cohort_enrolment  one row per enrolled subject — the denominator
#   cohort_visit_log  one row per subject per SCHEDULED visit, attended or not
#   cohort_outcome    one row per subject with a recorded final score, which is
#                     NOT the same set as the completers
#
# extra.sql issues three CREATE TABLE IF NOT EXISTS statements plus INSERTs and
# nothing else. It contains no DROP, ALTER, UPDATE or DELETE, so the eight tables
# already baked into turing.db — shared with other tasks in the suite — are left
# exactly as they are. The build-time assertion below re-checks that count.
COPY fixtures/extra.sql /tmp/

# Load through python3's bundled sqlite3 module rather than the sqlite3 CLI. The
# CLI is not guaranteed to be on PATH in the base image, and a missing binary
# fails the layer with no usable error, which surfaces only as BUILD_FAILED.
# python3 is present because the sandbox itself runs on it.
RUN python3 -c "import sqlite3,sys; c=sqlite3.connect('/data/db/turing.db'); c.executescript(open('/tmp/extra.sql').read()); c.commit(); c.close()" \
 && rm /tmp/extra.sql

# Fail the build rather than ship a silently empty fixture. These assert the
# fixture's OWN rows only: 133 outcome rows against 180 enrolments is the gap the
# whole task is about. Deliberately no assertion on the total table count of the
# database - that would couple this build to how many tables the base image
# happens to ship, and a pinned image gaining one table would fail the build here
# for a reason that has nothing to do with this fixture. extra.sql contains no
# DROP, ALTER, UPDATE or DELETE, so the baked tables cannot be disturbed anyway.
RUN python3 -c "import sqlite3,sys; c=sqlite3.connect('/data/db/turing.db'); q=lambda s: c.execute(s).fetchone()[0]; got=(q('SELECT COUNT(*) FROM cohort_enrolment'), q('SELECT COUNT(*) FROM cohort_visit_log'), q('SELECT COUNT(*) FROM cohort_outcome'), q(\"SELECT COUNT(*) FROM cohort_visit_log WHERE visit_type='END_OF_STUDY' AND attended=1\")); sys.exit(0) if got==(180,720,133,134) else sys.exit('fixture assertion failed: '+repr(got))"
