#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# build_fixture.sh — revert-reland-divergence
#
# Emits, into the directory this script lives in:
#   pipeline-svc.bundle   a full-history git bundle (never --depth 1) of a
#                         synthetic service repository: three authors, merge
#                         commits, an unmerged hotfix branch, a file rename,
#                         lightweight AND annotated tags, and a CHANGELOG.md
#                         that serves as the draft release notes under audit.
#   GROUND_TRUTH.md       written by the read-back stage at the bottom of this
#                         file, which CLONES THE BUNDLE into a scratch directory
#                         and runs the same git commands an agent would run.
#
# DETERMINISM: commit SHAs hash content, message, author, committer and BOTH
# timestamps, so every one of those is pinned here:
#   * author and committer identity are set per commit through `who`.
#   * GIT_AUTHOR_DATE and GIT_COMMITTER_DATE are both set, per commit, to a
#     value derived arithmetically from the commit index (raw `@<epoch> +0000`
#     form, so no locale or timezone can leak in).
#   * annotated tags take their tagger identity and date from the committer
#     environment, which is pinned at the point the tag is created.
#   * `git commit` runs with --no-gpg-sign and a scratch HOME so no user config
#     participates.
# Every object SHA therefore reproduces. The bundle's BYTES do not: pack
# encoding varies with git version and delta scheduling, so treat the committed
# bundle as the artefact of record and re-run this script for the read-back.
#
# PORTABILITY: no `sed -i` (BSD sed wants a mandatory backup suffix) and no
# `tac` (absent on macOS). See `setver` and the read-back stage.
#
# Run:  bash build_fixture.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

WORK="$(mktemp -d)"
export HOME="$WORK/home"; mkdir -p "$HOME"          # no ambient git config
export GIT_CONFIG_GLOBAL="$HOME/.gitconfig"
export GIT_CONFIG_SYSTEM=/dev/null
export TZ=UTC
export LC_ALL=C

# Three authors. A single-author repository makes "who touched this" free, and
# release forensics on a real service never is.
who() {
  case "$1" in
    priya)  n="Priya Raghunathan"; e="priya.raghunathan@example.invalid" ;;
    marcus) n="Marcus Lindqvist";  e="marcus.lindqvist@example.invalid"  ;;
    aiko)   n="Aiko Tanabe";       e="aiko.tanabe@example.invalid"       ;;
    *) echo "unknown author $1" >&2; exit 1 ;;
  esac
  export GIT_AUTHOR_NAME="$n"    GIT_AUTHOR_EMAIL="$e"
  export GIT_COMMITTER_NAME="$n" GIT_COMMITTER_EMAIL="$e"
}

REPO="$WORK/pipeline-svc"
mkdir -p "$REPO/src" "$REPO/tests" "$REPO/docs"
cd "$REPO"
who priya
git init -q -b main .

BASE_TS=1704704400          # 2024-01-08T09:00:00Z
i=0
stamp() {
  i=$((i + 1))
  local ts=$(( BASE_TS + (i - 1) * 259200 + (i % 5) * 3600 ))
  export GIT_AUTHOR_DATE="@${ts} +0000"
  export GIT_COMMITTER_DATE="@${ts} +0000"
}
cm() {                      # cm "<subject>" ["<body>"]
  stamp
  git add -A
  if [ "$#" -ge 2 ]; then
    git commit -q --no-gpg-sign -m "$1" -m "$2"
  else
    git commit -q --no-gpg-sign -m "$1"
  fi
  printf '%3d %s %s\n' "$i" "$(git rev-parse --short=12 HEAD)" "$1" >> "$WORK/plan.txt"
}
mrg() {                     # mrg "<subject>" <branch>
  stamp
  git merge -q --no-ff --no-gpg-sign -m "$1" "$2"
  printf '%3d %s %s\n' "$i" "$(git rev-parse --short=12 HEAD)" "$1" >> "$WORK/plan.txt"
}
al() { printf '%s\n' "$2" >> "$1"; }        # append a line

# Bump the VERSION line. NOT `sed -i`: BSD sed reads the next argument as a
# mandatory backup suffix, so the GNU form silently breaks on macOS. Writing to a
# scratch file and catting it back edits in place on both, and `cat >` truncates
# rather than replaces the inode, so the file mode git records never changes.
setver() {
  sed "s/^VERSION = .*/VERSION = \"$1\"/" src/config.py > "$WORK/config.ver"
  cat "$WORK/config.ver" > src/config.py
}

# ── src/pool.py revisions ───────────────────────────────────────────────────
pool_base() { cat > src/pool.py <<'EOF'
"""Connection pool shared by the ingest workers."""

import threading


class ConnectionPool:
    """A tiny idle-connection cache. Not thread-fair, but it is thread-safe."""

    def __init__(self, factory, min_size=2, max_size=32):
        self.factory = factory
        self.min_size = min_size
        self.max_size = max_size
        self._idle = []
        self._lock = threading.Lock()

    def acquire(self):
        with self._lock:
            if self._idle:
                return self._idle.pop()
        return self.factory()

    def release(self, conn):
        with self._lock:
            if len(self._idle) < self.max_size:
                self._idle.append(conn)
                return
        conn.close()

    def size(self):
        with self._lock:
            return len(self._idle)
EOF
}

# The steady state the pre-warm keeps being added to and removed from.
pool_timeout() { cat > src/pool.py <<'EOF'
"""Connection pool shared by the ingest workers."""

import threading


class ConnectionPool:
    """A tiny idle-connection cache. Not thread-fair, but it is thread-safe."""

    def __init__(self, factory, min_size=2, max_size=32, acquire_timeout=5.0):
        self.factory = factory
        self.min_size = min_size
        self.max_size = max_size
        self.acquire_timeout = acquire_timeout
        self._idle = []
        self._lock = threading.Lock()

    def acquire(self):
        if not self._lock.acquire(timeout=self.acquire_timeout):
            raise TimeoutError("pool lock not acquired within acquire_timeout")
        try:
            if self._idle:
                return self._idle.pop()
        finally:
            self._lock.release()
        return self.factory()

    def release(self, conn):
        with self._lock:
            if len(self._idle) < self.max_size:
                self._idle.append(conn)
                return
        conn.close()

    def size(self):
        with self._lock:
            return len(self._idle)
EOF
}

pool_prewarm() {            # $1 = the argument handed to _prewarm
  pool_timeout
  cat >> src/pool.py <<EOF


    def _prewarm(self, count):
        """Open connections up to \`count\` before any request arrives."""
        with self._lock:
            while len(self._idle) < count:
                self._idle.append(self.factory())

    def start(self):
        self._prewarm(self.$1)
EOF
}

pool_target() {             # the third implementation: warm target from config
  pool_timeout
  cat >> src/pool.py <<'EOF'


    def _prewarm(self, count):
        """Open connections up to `count` before any request arrives."""
        with self._lock:
            while len(self._idle) < count:
                self._idle.append(self.factory())

    def warm_target(self):
        """Resolve the configured warm target to a connection count."""
        from src.config import POOL_WARM_TARGET

        if POOL_WARM_TARGET == "max":
            return self.max_size
        if POOL_WARM_TARGET == "off":
            return 0
        return self.min_size

    def start(self):
        self._prewarm(self.warm_target())
EOF
}

# ── the backoff policy: src/retry.py, later renamed to src/backoff.py ───────
retry_v1() { cat > "$1" <<'EOF'
"""Retry helper for upstream calls."""


class RetryPolicy:
    def __init__(self, attempts=4, base_delay=0.25):
        self.attempts = attempts
        self.base_delay = base_delay

    def delay_for(self, attempt):
        return self.base_delay * (2 ** attempt)

    def should_retry(self, status):
        return status in (429, 500, 502, 503, 504)
EOF
}
retry_capped() { cat > "$1" <<'EOF'
"""Retry helper for upstream calls."""


class RetryPolicy:
    def __init__(self, attempts=4, base_delay=0.25, max_delay=30.0):
        self.attempts = attempts
        self.base_delay = base_delay
        self.max_delay = max_delay

    def delay_for(self, attempt):
        base = self.base_delay * (2 ** attempt)
        return min(self.max_delay, base)

    def should_retry(self, status):
        return status in (429, 500, 502, 503, 504)
EOF
}
retry_jitter() { cat > "$1" <<'EOF'
"""Retry helper for upstream calls."""

import random


class RetryPolicy:
    def __init__(self, attempts=4, base_delay=0.25, max_delay=30.0):
        self.attempts = attempts
        self.base_delay = base_delay
        self.max_delay = max_delay

    def delay_for(self, attempt):
        base = self.base_delay * (2 ** attempt)
        jittered = base * (0.5 + random.random())
        return min(self.max_delay, jittered)

    def should_retry(self, status):
        return status in (429, 500, 502, 503, 504)
EOF
}
# What the double-revert subject actually ships: a note, and no randomness.
retry_note() { cat > "$1" <<'EOF'
"""Retry helper for upstream calls."""


class RetryPolicy:
    def __init__(self, attempts=4, base_delay=0.25, max_delay=30.0):
        self.attempts = attempts
        self.base_delay = base_delay
        self.max_delay = max_delay

    def delay_for(self, attempt):
        # Jitter needs an injectable clock before it can come back; the replay
        # harness asserts exact delays and a seeded source is not wired up yet.
        base = self.base_delay * (2 ** attempt)
        return min(self.max_delay, base)

    def should_retry(self, status):
        return status in (429, 500, 502, 503, 504)
EOF
}

# ── CHANGELOG sections — this is the DRAFT RELEASE NOTES under audit ────────
cl_1_3_0() { cat <<'EOF'
## 1.3.0

- Initial extraction of the ingest pipeline from the monolith.
- Connection pool, retry policy and shard router.
EOF
}
cl_1_4_0() { cat <<'EOF'
## 1.4.0

- Configurable pool bounds (`POOL_MIN_SIZE`, `POOL_MAX_SIZE`).
- Bounded lock acquisition in the pool, with `acquire_timeout`.
EOF
}
cl_1_5_0() { cat <<'EOF'
## 1.5.0

- Retry policy honours an upper bound on the computed delay.
- Shard router reports per-shard lag.
EOF
}
cl_1_6_0() { cat <<'EOF'
## 1.6.0

- Health endpoint exposes pool occupancy.
- Runbook section on draining a worker.
EOF
}
cl_1_7_0() { cat <<'EOF'
## 1.7.0

- Structured request logging on the API surface.
- Test coverage for pool release-on-overflow.
EOF
}
cl_1_8_0() { cat <<'EOF'
## 1.8.0

- Shard router keeps a stable ordering across restarts.
- Shard rebalancing is now incremental.
EOF
}
cl_1_9_0() { cat <<'EOF'
## 1.9.0

- Connection-pool pre-warming on worker start.
- Runbook note on request logs.
EOF
}
cl_1_9_1() { cat <<'EOF'
## 1.9.1

- Hotfix: shard router guards against an empty routing table.
EOF
}
cl_1_10_0() { cat <<'EOF'
## 1.10.0

- Jittered exponential backoff in the retry loop, which removes the
  thundering-herd spike we saw whenever an upstream came back.
- The connection pool warms to the configured target on worker start.
- Config loader accepts a per-environment override file.
- Runbook: upstream-recovery checklist.
EOF
}
cl_1_11_0() { cat <<'EOF'
## 1.11.0

- Single-writer-per-shard mode for the archival path.
- API surface returns the resolved shard in every response.
- Pool metrics exported on the health endpoint.
EOF
}
write_changelog() {          # args: version slugs, newest first
  {
    echo "# Changelog"
    echo
    echo "Notable changes to pipeline-svc. Newest release first."
    echo
    for v in "$@"; do "cl_$v"; echo; done
  } > CHANGELOG.md
}

# ═══════════════════════════════════════════════════════════════════════════
#  History
# ═══════════════════════════════════════════════════════════════════════════

# ── 1. initial import ───────────────────────────────────────────────────────
cat > README.md <<'EOF'
# pipeline-svc

Ingest pipeline for the event platform. Owns the connection pool, the retry
policy and the shard router. Release process and history live in CHANGELOG.md.
EOF
cat > src/config.py <<'EOF'
"""Runtime configuration."""

SERVICE_NAME = "pipeline-svc"
VERSION = "1.3.0"
EOF
pool_base
retry_v1 src/retry.py
cat > src/shard.py <<'EOF'
"""Shard routing."""

SHARDS = ("a", "b", "c", "d")


def route(key):
    return SHARDS[hash(key) % len(SHARDS)]
EOF
cat > src/api.py <<'EOF'
"""HTTP surface."""

from src.pool import ConnectionPool


def health(pool: ConnectionPool):
    return {"status": "ok"}
EOF
cat > tests/test_pool.py <<'EOF'
from src.pool import ConnectionPool


class FakeConn:
    def close(self):
        pass


def test_acquire_returns_a_connection():
    pool = ConnectionPool(FakeConn)
    assert pool.acquire() is not None
EOF
cat > docs/runbook.md <<'EOF'
# Runbook

Operational notes for pipeline-svc.
EOF
write_changelog 1_3_0
cm "Initial import of pipeline-svc"

# ── 2. early history, releases 1.4.0 - 1.7.0 ────────────────────────────────
al src/api.py 'def occupancy(pool):'
al src/api.py '    return {"idle": pool.size()}'
cm "api: report idle connections"

al src/config.py 'POOL_MIN_SIZE = 2'
al src/config.py 'POOL_MAX_SIZE = 32'
cm "config: expose the pool bounds"

who marcus
pool_timeout
al tests/test_pool.py ''
al tests/test_pool.py 'def test_acquire_timeout_is_configurable():'
al tests/test_pool.py '    assert ConnectionPool(FakeConn, acquire_timeout=1.0).acquire_timeout == 1.0'
cm "pool: bound lock acquisition with acquire_timeout"
who priya

al docs/runbook.md ''
al docs/runbook.md '## Pool occupancy'
al docs/runbook.md ''
al docs/runbook.md 'Read the idle count from the health endpoint before draining.'
cm "docs: runbook note on pool occupancy"

write_changelog 1_4_0 1_3_0
cm "docs: changelog for 1.4.0"
setver 1.4.0
cm "release: 1.4.0"
git tag v1.4.0

retry_capped src/retry.py
cm "retry: cap the computed delay at max_delay"

al src/shard.py ''
al src/shard.py 'def lag(shard):'
al src/shard.py '    return 0'
cm "shard: stub per-shard lag reporting"

write_changelog 1_5_0 1_4_0 1_3_0
cm "docs: changelog for 1.5.0"
setver 1.5.0
cm "release: 1.5.0"
git tag v1.5.0

al src/api.py ''
al src/api.py 'def pool_occupancy(pool):'
al src/api.py '    return {"idle": pool.size(), "max": pool.max_size}'
cm "api: expose pool occupancy"

al docs/runbook.md ''
al docs/runbook.md '## Draining a worker'
al docs/runbook.md ''
al docs/runbook.md 'Stop accepting work, wait for the idle count to reach the floor, then exit.'
cm "docs: runbook section on draining"

al src/shard.py ''
al src/shard.py 'def rebalance(moves):'
al src/shard.py '    return moves[:1]'
cm "shard: incremental rebalancing"

write_changelog 1_6_0 1_5_0 1_4_0 1_3_0
cm "docs: changelog for 1.6.0"
setver 1.6.0
cm "release: 1.6.0"
git tag v1.6.0

who aiko
al src/api.py ''
al src/api.py 'def request_log(entry):'
al src/api.py '    return {"event": "request", **entry}'
cm "api: structured request logging"
who priya

al tests/test_pool.py ''
al tests/test_pool.py 'def test_release_on_overflow_closes():'
al tests/test_pool.py '    pool = ConnectionPool(FakeConn, max_size=0)'
al tests/test_pool.py '    pool.release(FakeConn())'
al tests/test_pool.py '    assert pool.size() == 0'
cm "tests: cover release on overflow"

al src/config.py 'REQUEST_TIMEOUT_S = 15.0'
cm "config: add a request timeout"

write_changelog 1_7_0 1_6_0 1_5_0 1_4_0 1_3_0
cm "docs: changelog for 1.7.0"
setver 1.7.0
cm "release: 1.7.0"
git tag v1.7.0

# ── 3. the pre-warm lands on a side branch and enters through a merge ───────
git checkout -q -b feature/prewarm
who marcus
pool_prewarm max_size
cm "Pre-warm the connection pool on worker start" \
"Cold start costs us the first few hundred milliseconds of every deploy
because every early request pays connection setup. Open the connections up
front in start() so the first request finds a warm pool."
PREWARM_1=$(git rev-parse HEAD)
who priya

git checkout -q main
al docs/runbook.md ''
al docs/runbook.md '## Request logs'
al docs/runbook.md ''
al docs/runbook.md 'Structured request entries land in the platform log sink.'
cm "docs: runbook note on request logs"

mrg "Merge branch 'feature/prewarm' into main" feature/prewarm
MERGE_PREWARM=$(git rev-parse HEAD)

al src/shard.py ''
al src/shard.py 'def stable_order(keys):'
al src/shard.py '    return sorted(keys)'
cm "shard: keep a stable ordering across restarts"

al src/api.py ''
al src/api.py 'def resolved_shard(key):'
al src/api.py '    from src.shard import route'
al src/api.py ''
al src/api.py '    return {"shard": route(key)}'
cm "api: report the resolved shard"
API_SHARD=$(git rev-parse HEAD)

pool_timeout
cm "Revert \"Pre-warm the connection pool on worker start\"" \
"This reverts the pre-warm change. On the deploy that carried it every worker
opened its full ceiling of connections simultaneously and we tripped the
upstream connection limit inside forty seconds. Reverting to unblock the
release; we will bring it back once the warm target is sane."
REVERT_1=$(git rev-parse HEAD)

write_changelog 1_8_0 1_7_0 1_6_0 1_5_0 1_4_0 1_3_0
cm "docs: changelog for 1.8.0"
setver 1.8.0
cm "release: 1.8.0"
git tag v1.8.0

# ── 4. the pre-warm comes back, claiming to be a cherry-pick of the original ─
al src/config.py 'POOL_WARM_TARGET = "min"'
cm "config: add a pool warm target knob"
WARM_KNOB=$(git rev-parse HEAD)

# Same subject as PREWARM_1, and a trailer naming it, but one line different.
# The committer is deliberately not the author.
who priya
export GIT_COMMITTER_NAME="Marcus Lindqvist"
export GIT_COMMITTER_EMAIL="marcus.lindqvist@example.invalid"
pool_prewarm min_size
cm "Pre-warm the connection pool on worker start" \
"Rolling this forward again for the 1.9 cycle now that there is a warm-target
knob to hang it off.

(cherry picked from commit $PREWARM_1)"
PREWARM_2=$(git rev-parse HEAD)
who priya

al tests/test_pool.py ''
al tests/test_pool.py 'def test_start_prewarms():'
al tests/test_pool.py '    pool = ConnectionPool(FakeConn)'
al tests/test_pool.py '    pool.start()'
al tests/test_pool.py '    assert pool.size() >= 1'
cm "tests: cover the warm pool on start-up"

write_changelog 1_9_0 1_8_0 1_7_0 1_6_0 1_5_0 1_4_0 1_3_0
cm "docs: changelog for 1.9.0"
setver 1.9.0
cm "release: 1.9.0"
git tag v1.9.0
REL_1_9_0=$(git rev-parse HEAD)

# ── 5. the 1.9.1 hotfix, cut from BEFORE the pre-warm came back ─────────────
git checkout -q -b hotfix/1.9.1 "$REVERT_1"
who aiko
al src/shard.py ''
al src/shard.py 'def route_safe(key):'
al src/shard.py '    if not SHARDS:'
al src/shard.py '        return None'
al src/shard.py '    return route(key)'
cm "shard: guard against an empty routing table"
HOTFIX_BRANCH=$(git rev-parse HEAD)
write_changelog 1_9_1 1_8_0 1_7_0 1_6_0 1_5_0 1_4_0 1_3_0
cm "docs: changelog for 1.9.1"
setver 1.9.1
cm "release: 1.9.1"
git tag v1.9.1
REL_1_9_1=$(git rev-parse HEAD)
who priya

# The same fix reaches main separately, with a faithful trailer this time.
git checkout -q main
who aiko
al src/shard.py ''
al src/shard.py 'def route_safe(key):'
al src/shard.py '    if not SHARDS:'
al src/shard.py '        return None'
al src/shard.py '    return route(key)'
write_changelog 1_9_1 1_9_0 1_8_0 1_7_0 1_6_0 1_5_0 1_4_0 1_3_0
cm "shard: guard against an empty routing table" \
"Forward-port of the 1.9.1 hotfix onto main.

(cherry picked from commit $HOTFIX_BRANCH)"
HOTFIX_MAIN=$(git rev-parse HEAD)
who priya

# ── 6. the backoff policy is renamed, then churns ──────────────────────────
git mv src/retry.py src/backoff.py
cm "retry: move the backoff policy to src/backoff.py"
RENAME=$(git rev-parse HEAD)

cat > tests/test_backoff.py <<'EOF'
from src.backoff import RetryPolicy


def test_delay_grows():
    policy = RetryPolicy()
    assert policy.delay_for(0) == 0.25
    assert policy.delay_for(1) == 0.5


def test_delay_is_capped():
    policy = RetryPolicy(max_delay=1.0)
    assert policy.delay_for(10) == 1.0
EOF
cm "tests: assert exact delays in the replay harness"

who marcus
retry_jitter src/backoff.py
cm "Add jittered exponential backoff to the retry loop" \
"Every client retries on the same schedule, so an upstream coming back gets a
synchronised wall of traffic. Scatter the computed delay so the herd spreads."
JITTER=$(git rev-parse HEAD)
who priya

retry_capped src/backoff.py
cm "Revert \"Add jittered exponential backoff to the retry loop\"" \
"This reverts the jitter change. The replay harness is seeded and asserts
exact delays, so a non-deterministic delay_for() makes the whole suite flap.
Reverting for now; needs an injectable random source before it can go back in."
JITTER_REVERT=$(git rev-parse HEAD)

# Subject says the jitter is back. The diff adds a comment.
who marcus
retry_note src/backoff.py
cm "Revert \"Revert \\\"Add jittered exponential backoff to the retry loop\\\"\"" \
"Bringing the jitter change back for the 1.10 cycle now that the harness can
inject its own clock."
JITTER_REREVERT=$(git rev-parse HEAD)
who priya

al src/config.py 'OVERRIDE_FILE = "config.local.toml"'
cm "config: accept a per-environment override file"

al docs/runbook.md ''
al docs/runbook.md '## Upstream recovery'
al docs/runbook.md ''
al docs/runbook.md 'When an upstream returns, watch the retry delay spread before lifting caps.'
cm "docs: runbook upstream-recovery checklist"

# ── 7. the pre-warm is removed a second time, without saying so ────────────
who aiko
pool_timeout
cm "pool: simplify worker start-up" \
"Worker start-up has accumulated more moving parts than it needs. Take the
start-up path back to the plain constructor and let the pool fill on demand."
PREWARM_REMOVED_2=$(git rev-parse HEAD)
who priya

write_changelog 1_10_0 1_9_1 1_9_0 1_8_0 1_7_0 1_6_0 1_5_0 1_4_0 1_3_0
cm "docs: changelog for 1.10.0"
# The 1.10.0 tag is cut HERE, before the version bump: the tagged tree still
# says VERSION = "1.9.0".
git tag -a v1.10.0 -m "pipeline-svc 1.10.0"
REL_1_10_0=$(git rev-parse HEAD)
setver 1.10.0
cm "release: bump VERSION to 1.10.0"

# ── 8. the pre-warm returns a third time, differently ──────────────────────
who marcus
pool_target
cm "pool: warm the pool to the configured target" \
"Bring the warm-up back, driven by POOL_WARM_TARGET rather than a hard-coded
bound, so the ceiling case that broke us earlier in the cycle cannot be
selected by accident."
PREWARM_3=$(git rev-parse HEAD)
who priya

al tests/test_pool.py ''
al tests/test_pool.py 'def test_warm_target_defaults_to_min():'
al tests/test_pool.py '    pool = ConnectionPool(FakeConn, min_size=3)'
al tests/test_pool.py '    pool.start()'
al tests/test_pool.py '    assert pool.size() == 3'
cm "tests: pin the warm target to the configured value"

stamp
git commit -q --no-gpg-sign --allow-empty -m "chore: retrigger the release pipeline"

who marcus
al src/shard.py ''
al src/shard.py 'class SingleWriterShard:'
al src/shard.py '    """One archival writer per shard, with an explicit owner claim."""'
al src/shard.py ''
al src/shard.py '    def __init__(self, shard, owner):'
al src/shard.py '        self.shard = shard'
al src/shard.py '        self.owner = owner'
al src/shard.py ''
al src/shard.py '    def claim(self, owner):'
al src/shard.py '        if self.owner is None:'
al src/shard.py '            self.owner = owner'
al src/shard.py '        return self.owner == owner'
cm "Revert to a single writer per shard" \
"Concurrent archival writers interleave and the compactor cannot tell which
segment is authoritative. Move the archival path back to one writer per shard
by adding an explicit owner claim."
DECOY=$(git rev-parse HEAD)
who priya

# A subject that promises metrics. The diff is a note.
al src/api.py ''
al src/api.py '# TODO(metrics): export pool counters here once the platform sink accepts'
al src/api.py '# gauges. Nothing is emitted yet.'
cm "api: prepare the pool metrics export"
METRICS_SUBJECT=$(git rev-parse HEAD)

al src/api.py ''
al src/api.py 'def version():'
al src/api.py '    from src.config import VERSION'
al src/api.py ''
al src/api.py '    return {"version": VERSION}'
cm "api: expose the running version"

al src/api.py ''
al src/api.py 'def shard_owner(shard_state):'
al src/api.py '    return {"owner": shard_state.owner}'
cm "api: report the archival owner"

al docs/runbook.md ''
al docs/runbook.md '## Single-writer archival'
al docs/runbook.md ''
al docs/runbook.md 'Confirm the owner claim before replaying a segment.'
cm "docs: runbook note on single-writer archival"

git tag pipeline-1.11-rc1

write_changelog 1_11_0 1_10_0 1_9_1 1_9_0 1_8_0 1_7_0 1_6_0 1_5_0 1_4_0 1_3_0
cm "docs: changelog for 1.11.0"
setver 1.11.0
cm "release: 1.11.0"
git tag -a v1.11.0 -m "pipeline-svc 1.11.0"
REL_1_11_0=$(git rev-parse HEAD)

al docs/runbook.md ''
al docs/runbook.md '## Release sign-off'
al docs/runbook.md ''
al docs/runbook.md 'Reconcile the changelog against the tagged trees before approving.'
cm "docs: runbook note on release sign-off"
HEAD_SHA=$(git rev-parse HEAD)

echo "HEAD = $HEAD_SHA"

# ═══════════════════════════════════════════════════════════════════════════
#  BUNDLE
# ═══════════════════════════════════════════════════════════════════════════
rm -f "$HERE/pipeline-svc.bundle"
git bundle create -q "$HERE/pipeline-svc.bundle" --all

# ═══════════════════════════════════════════════════════════════════════════
#  READ-BACK STAGE — clone the bundle and interrogate the clone
# ═══════════════════════════════════════════════════════════════════════════
CLONE="$WORK/readback"
rm -rf "$CLONE"
git clone -q "$HERE/pipeline-svc.bundle" "$CLONE"
cd "$CLONE"
git checkout -q -B main "$HEAD_SHA"

short() { git rev-parse --short=12 "$1"; }
blob()  { git rev-parse "$1" | cut -c1-12; }
same()  { [ "$(git rev-parse "$1")" = "$(git rev-parse "$2")" ] && echo IDENTICAL || echo DIFFERENT; }
haspw() { git show "$1:src/pool.py" | grep -c 'def start' || true; }
warmarg() { git show "$1:src/pool.py" | sed -n 's/^ *self\._prewarm(\(.*\))$/\1/p' | head -1; }

{
cat <<HDR
# GROUND_TRUTH.md — revert-reland-divergence

Everything below is the **output of git commands run against a fresh clone of
\`pipeline-svc.bundle\`**, not against the builder's working tree. \`bash
build_fixture.sh\` rebuilds the bundle and regenerates this file; the SHAs below
are therefore the SHAs an agent will see.

Read-back procedure:

\`\`\`
git clone pipeline-svc.bundle readback
cd readback && git checkout -B main $HEAD_SHA
\`\`\`

## Shape of the repository

- pinned branch tip (the SHA \`environment/Dockerfile\` checks out as \`main\`):
  \`$HEAD_SHA\`
- \`git cat-file -t $HEAD_SHA\` in the clone -> \`$(git cat-file -t "$HEAD_SHA")\`
- \`git rev-list --count HEAD\` -> **$(git rev-list --count HEAD)** commits
- \`git rev-list --count --merges HEAD\` -> **$(git rev-list --count --merges HEAD)** merge commit
- \`git rev-list --count --first-parent HEAD\` -> **$(git rev-list --count --first-parent HEAD)**, so
  $(( $(git rev-list --count HEAD) - $(git rev-list --count --first-parent HEAD) )) commit(s) are reachable only off the first-parent line
- \`git rev-list --count --all\` -> **$(git rev-list --count --all)** (the unmerged hotfix branch adds commits
  that \`HEAD\` cannot see)
- branches in the clone: $(git branch -a --format='%(refname:short)' | tr '\n' ' ')
- tracked files at HEAD ($(git ls-files | wc -l | tr -d ' ')):
$(git ls-files | sed 's/^/  - `/;s/$/`/')
- authors: $(git log --all --format='%an' | sort -u | tr '\n' ';' | sed 's/;/; /g')
- one commit's author is not its committer:
  \`$(git log --format='%h author=%an committer=%cn' --all | awk -F'author=| committer=' '$2 != $3 {print $1 " " $2 "/" $3}' | head -1)\`
- first commit $(git log --reverse --format='%ad' --date=short | head -1), last commit $(git log -1 --format='%ad' --date=short)

### Tags

\`git tag\` (git's own default ordering — lexical, and one tag is not a version):

\`\`\`
$(git tag)
\`\`\`

\`git tag | sort -V\`:

\`\`\`
$(git tag | sort -V)
\`\`\`

Tag types and targets:

$(for t in $(git tag | sort -V); do printf '  - `%s` -> %s object, commit `%s`, VERSION at that tag = %s, subject: %s\n' "$t" "$(git cat-file -t "refs/tags/$t")" "$(short "${t}^{commit}")" "$(git show "$t:src/config.py" | sed -n 's/^VERSION = //p')" "$(git log -1 --format='%s' "${t}^{commit}")"; done)

**\`v1.10.0\` and \`v1.11.0\` are annotated tags; the rest are lightweight.**
Note the \`VERSION\` column: at \`v1.10.0\` the tagged tree still says
$(git show v1.10.0:src/config.py | sed -n 's/^VERSION = //p'), because the tag was cut before the version bump commit
\`$(short "$(git rev-list -1 --grep='release: bump VERSION to 1.10.0' HEAD)")\`.

## Every commit whose subject mentions a revert

\`git log --all --format='%h %ad %s' --date=short --grep='[Rr]evert'\`:

\`\`\`
$(git log --all --format='%h %ad %s' --date=short --grep='[Rr]evert')
\`\`\`

Of those, the ones that actually remove the thing their subject names:
\`$(short "$REVERT_1")\` and \`$(short "$JITTER_REVERT")\`. The other two are traps.
And the pre-warm's **second** removal, \`$(short "$PREWARM_REMOVED_2")\`, does not appear in this
list at all, because its subject never says "revert".

## Layer 1 — the pre-warm churns three times, not once

\`git log --format='%h %ad %s' --date=short -- src/pool.py\`:

\`\`\`
$(git log --format='%h %ad %s' --date=short -- src/pool.py)
\`\`\`

| step | role | full SHA | short | date | author |
|---|---|---|---|---|---|
| 1 | first landing (on a side branch) | \`$PREWARM_1\` | \`$(short "$PREWARM_1")\` | $(git log -1 --format='%ad' --date=short "$PREWARM_1") | $(git log -1 --format='%an' "$PREWARM_1") |
| 2 | merge that brought it to main | \`$MERGE_PREWARM\` | \`$(short "$MERGE_PREWARM")\` | $(git log -1 --format='%ad' --date=short "$MERGE_PREWARM") | $(git log -1 --format='%an' "$MERGE_PREWARM") |
| 3 | first removal (a true revert) | \`$REVERT_1\` | \`$(short "$REVERT_1")\` | $(git log -1 --format='%ad' --date=short "$REVERT_1") | $(git log -1 --format='%an' "$REVERT_1") |
| 4 | second landing (claims to be a cherry-pick) | \`$PREWARM_2\` | \`$(short "$PREWARM_2")\` | $(git log -1 --format='%ad' --date=short "$PREWARM_2") | $(git log -1 --format='%an' "$PREWARM_2") |
| 5 | second removal (subject says nothing) | \`$PREWARM_REMOVED_2\` | \`$(short "$PREWARM_REMOVED_2")\` | $(git log -1 --format='%ad' --date=short "$PREWARM_REMOVED_2") | $(git log -1 --format='%an' "$PREWARM_REMOVED_2") |
| 6 | third landing (a different design) | \`$PREWARM_3\` | \`$(short "$PREWARM_3")\` | $(git log -1 --format='%ad' --date=short "$PREWARM_3") | $(git log -1 --format='%an' "$PREWARM_3") |

### The first landing is not on the first-parent line

- \`git merge-base --is-ancestor $(short "$PREWARM_1") HEAD\` -> ancestor: yes
- \`git rev-list --first-parent HEAD | grep -c $(short "$PREWARM_1")\` -> $(git rev-list --first-parent HEAD | grep -c "$PREWARM_1" || true)
- parents of the merge \`$(short "$MERGE_PREWARM")\`: $(git log -1 --format='%p' "$MERGE_PREWARM")
- \`git log --oneline --first-parent -- src/pool.py\` (what a first-parent read shows):

\`\`\`
$(git log --oneline --first-parent -- src/pool.py)
\`\`\`

Neither of the two obvious views is complete. The default
\`git log -- src/pool.py\` lists the side-branch landing \`$(short "$PREWARM_1")\` but **not** the
merge \`$(short "$MERGE_PREWARM")\` — history simplification drops a merge that is TREESAME to a
parent — while \`--first-parent\` lists the merge but **not** the landing. The
sequence is only complete if both are read.

The history also carries one empty commit, which has no diff at all:

\`\`\`
$(git log --format='%h %ad %s' --date=short -1 --grep='retrigger the release pipeline') -> changed paths: $(git diff --numstat "$(git rev-list -1 --grep='retrigger the release pipeline' HEAD)^" "$(git rev-list -1 --grep='retrigger the release pipeline' HEAD)" | wc -l | tr -d ' ')
\`\`\`

### Recorded reason for the first removal

\`git log -1 --format='%b' $(short "$REVERT_1")\`:

\`\`\`
$(git log -1 --format='%b' "$REVERT_1")
\`\`\`

It is a genuine back-out, checked by content and not by the subject:
\`src/pool.py\` at the removal versus at the parent of the first landing —
\`$(blob "$REVERT_1:src/pool.py")\` vs \`$(blob "$PREWARM_1^:src/pool.py")\` -> $(same "$REVERT_1:src/pool.py" "$PREWARM_1^:src/pool.py")

## Layer 2 — the second landing lies about being a cherry-pick

Body of \`$(short "$PREWARM_2")\`:

\`\`\`
$(git log -1 --format='%b' "$PREWARM_2")
\`\`\`

The trailer names \`$(short "$PREWARM_1")\`. The two are not the same change:

\`git diff $(short "$PREWARM_1") $(short "$PREWARM_2") -- src/pool.py\`:

\`\`\`
$(git diff "$PREWARM_1" "$PREWARM_2" -- src/pool.py)
\`\`\`

- path-scoped \`--numstat\`: \`$(git diff --numstat "$PREWARM_1" "$PREWARM_2" -- src/pool.py)\`
- whole-tree \`--shortstat\` between the same two commits:
  \`$(git diff --shortstat "$PREWARM_1" "$PREWARM_2" | sed 's/^ *//')\`
- pool blobs: \`$(blob "$PREWARM_1:src/pool.py")\` at the first landing,
  \`$(blob "$PREWARM_2:src/pool.py")\` at the second

### Neither the subject nor the diffstat separates them

- both subjects are byte-identical:
  \`$(git log -1 --format='%s' "$PREWARM_1")\`
- \`git log --all --format='%h %an %s' --grep='^Pre-warm the connection pool on worker start\$'\`:

\`\`\`
$(git log --all --format='%h %an %s' --grep='^Pre-warm the connection pool on worker start$')
\`\`\`

- each commit read on its own:

\`\`\`
$(git show --numstat --format='%h %s' "$PREWARM_1" | sed '/^$/d')
$(git show --numstat --format='%h %s' "$PREWARM_2" | sed '/^$/d')
\`\`\`

  Both are **10 insertions, 0 deletions in \`src/pool.py\` and nothing else**.

### The numbers the difference has to be read against

\`\`\`
$(git show HEAD:src/pool.py | grep -n 'def __init__' | sed 's/^/  /')
\`\`\`

\`max_size\` is 32 and \`min_size\` is 2, and \`$(short "$WARM_KNOB")\`
($(git log -1 --format='%ad' --date=short "$WARM_KNOB"), "$(git log -1 --format='%s' "$WARM_KNOB")") had added
\`$(git show HEAD:src/config.py | grep POOL_WARM_TARGET)\` immediately before the second landing.

## Layer 3 — the second removal never says "revert"

\`git show --stat --format='%H%n%an%n%ad%n%s%n%n%b' --date=short $(short "$PREWARM_REMOVED_2")\`:

\`\`\`
$(git show --stat --format='%H%n%an%n%ad%n%s%n%n%b' --date=short "$PREWARM_REMOVED_2" | head -30)
\`\`\`

- \`git diff --numstat $(short "$PREWARM_REMOVED_2")^ $(short "$PREWARM_REMOVED_2")\` -> \`$(git diff --numstat "$PREWARM_REMOVED_2^" "$PREWARM_REMOVED_2")\`
- it deletes \`_prewarm()\` and \`start()\`: \`grep -c 'def start'\` on \`src/pool.py\` goes
  from $(haspw "$PREWARM_REMOVED_2^") at its parent to $(haspw "$PREWARM_REMOVED_2") at the commit
- the pool module lands back on the blob it had before the second landing:
  \`$(blob "$PREWARM_REMOVED_2:src/pool.py")\` vs \`$(blob "$PREWARM_2^:src/pool.py")\` -> $(same "$PREWARM_REMOVED_2:src/pool.py" "$PREWARM_2^:src/pool.py")

## Layer 4 — the third landing is a third design

\`git show --format='%b' --stat $(short "$PREWARM_3")\`:

\`\`\`
$(git show --format='%b' --stat "$PREWARM_3" | head -20)
\`\`\`

\`git diff $(short "$PREWARM_2") $(short "$PREWARM_3") -- src/pool.py\`:

\`\`\`
$(git diff "$PREWARM_2" "$PREWARM_3" -- src/pool.py)
\`\`\`

The argument handed to \`_prewarm\` at each landing:

- $(short "$PREWARM_1") -> \`$(warmarg "$PREWARM_1")\`
- $(short "$PREWARM_2") -> \`$(warmarg "$PREWARM_2")\`
- $(short "$PREWARM_3") -> \`$(warmarg "$PREWARM_3")\`, resolved by a new \`warm_target()\` method
  that reads \`POOL_WARM_TARGET\` and can also select \`max_size\` or 0

So no two of the three landings are the same change, and the survivor is the
only one that is configuration-driven.

## Layer 5 — which releases actually shipped a pre-warm

\`grep -c 'def start' src/pool.py\` at each tag, in semantic order:

$(for t in $(git tag | sort -V); do printf '  - `%s` -> %s' "$t" "$(haspw "$t")"; a=$(warmarg "$t"); [ -n "$a" ] && printf ', warms `%s`' "$a"; printf '\n'; done)

- \`git tag --contains $(short "$PREWARM_2")\` -> \`$(git tag --contains "$PREWARM_2" | tr '\n' ' ')\`
- \`git tag --contains $(short "$PREWARM_3")\` -> \`$(git tag --contains "$PREWARM_3" | tr '\n' ' ')\`
- \`git tag --contains $(short "$PREWARM_1")\` -> \`$(git tag --contains "$PREWARM_1" | tr '\n' ' ')\`

**Commit containment is not release presence.** \`$(short "$PREWARM_1")\` is an ancestor of
\`v1.8.0\` and \`v1.9.1\`, so \`git tag --contains\` lists both, yet \`grep -c 'def start'\`
on \`src/pool.py\` is $(haspw v1.8.0) at \`v1.8.0\` and $(haspw v1.9.1) at \`v1.9.1\`: the commit is reachable and its
effect is not, because the removal is reachable too. A model that answers this
question with \`--contains\` alone gets it wrong in both directions.

Read carefully: the pre-warm shipped in **v1.9.0**, was **absent again in
v1.10.0** because \`$(short "$PREWARM_REMOVED_2")\` removed it before that tag was cut, and came back
in **v1.11.0** in its third form. "First shipped in v1.9.0 and present ever
since" is false. The earliest tag containing the surviving implementation is
\`$(git tag --contains "$PREWARM_3" | sort -V | head -1)\` by \`sort -V\`, which is a release *candidate* tag and not a
release; the first release carrying it is \`v1.11.0\`.

### v1.9.1 is not a descendant of v1.9.0

- \`git merge-base --is-ancestor v1.9.0 v1.9.1\` -> $(git merge-base --is-ancestor v1.9.0 v1.9.1 && echo yes || echo no)
- \`git merge-base --is-ancestor $(short "$PREWARM_2") v1.9.1\` -> $(git merge-base --is-ancestor "$PREWARM_2" v1.9.1 && echo yes || echo no)
- the hotfix branch was cut from \`$(short "$REVERT_1")\`, the first removal, so it never carried a
  pre-warm at all: \`grep -c 'def start'\` at \`v1.9.1\` -> $(haspw v1.9.1)
- \`git log --oneline v1.9.0..v1.9.1\` (what 1.9.1 has that 1.9.0 does not):

\`\`\`
$(git log --oneline v1.9.0..v1.9.1)
\`\`\`

- \`git log --oneline v1.9.1..v1.9.0\` (what 1.9.1 is missing):

\`\`\`
$(git log --oneline v1.9.1..v1.9.0)
\`\`\`

The same hotfix exists twice, as two different commits: \`$(short "$HOTFIX_BRANCH")\` on the
branch and \`$(short "$HOTFIX_MAIN")\` on main, same subject
("$(git log -1 --format='%s' "$HOTFIX_MAIN")"), and the second carries a
faithful cherry-pick trailer naming the first.

## Layer 6 — the backoff policy was renamed, then churned

\`git log --format='%h %ad %s' --date=short -- src/backoff.py\` (no \`--follow\`):

\`\`\`
$(git log --format='%h %ad %s' --date=short -- src/backoff.py)
\`\`\`

\`git log --follow --format='%h %ad %s' --date=short -- src/backoff.py\`:

\`\`\`
$(git log --follow --format='%h %ad %s' --date=short -- src/backoff.py)
\`\`\`

The rename is \`$(short "$RENAME")\` ("$(git log -1 --format='%s' "$RENAME")"), and
\`git show --stat\` on it reports a pure rename:

\`\`\`
$(git show --stat --format='' -M "$RENAME" | sed '/^$/d')
\`\`\`

| role | full SHA | short | date | author |
|---|---|---|---|---|
| jitter landed | \`$JITTER\` | \`$(short "$JITTER")\` | $(git log -1 --format='%ad' --date=short "$JITTER") | $(git log -1 --format='%an' "$JITTER") |
| jitter removed | \`$JITTER_REVERT\` | \`$(short "$JITTER_REVERT")\` | $(git log -1 --format='%ad' --date=short "$JITTER_REVERT") | $(git log -1 --format='%an' "$JITTER_REVERT") |
| "brought back" | \`$JITTER_REREVERT\` | \`$(short "$JITTER_REREVERT")\` | $(git log -1 --format='%ad' --date=short "$JITTER_REREVERT") | $(git log -1 --format='%an' "$JITTER_REREVERT") |

Removal reason (\`$(short "$JITTER_REVERT")\`):

\`\`\`
$(git log -1 --format='%b' "$JITTER_REVERT")
\`\`\`

### The double-revert restores nothing

Subject of \`$(short "$JITTER_REREVERT")\`:

\`\`\`
$(git log -1 --format='%s%n%n%b' "$JITTER_REREVERT")
\`\`\`

\`git show --format='' $(short "$JITTER_REREVERT")\`:

\`\`\`
$(git show --format='' "$JITTER_REREVERT")
\`\`\`

- \`grep -c random\` on the backoff module: $(git show "$JITTER:src/backoff.py" | grep -c random || true) at \`$(short "$JITTER")\`,
  $(git show "$JITTER_REVERT:src/backoff.py" | grep -c random || true) at \`$(short "$JITTER_REVERT")\`,
  $(git show "$JITTER_REREVERT:src/backoff.py" | grep -c random || true) at \`$(short "$JITTER_REREVERT")\` — the "revert of the revert" adds none
- at the tags: v1.10.0 -> $(git show v1.10.0:src/backoff.py | grep -c random || true), v1.11.0 -> $(git show v1.11.0:src/backoff.py | grep -c random || true), HEAD -> $(git show HEAD:src/backoff.py | grep -c random || true)
- the delay computation at HEAD is the pre-jitter one. Everything the module
  gained since the jitter left is comment text:
  \`git diff --numstat $(short "$JITTER^") HEAD -- src/backoff.py\` -> \`$(git diff --numstat "$JITTER^" HEAD -- src/backoff.py)\`, and
  the inserted lines are

\`\`\`
$(git diff "$JITTER^" HEAD -- src/backoff.py | grep '^+' | grep -v '^+++' | sed 's/^/  /')
\`\`\`

- blobs: \`$(blob HEAD:src/backoff.py)\` at HEAD versus \`$(blob "$JITTER^:src/backoff.py")\` before the jitter landed,
  and \`$(blob "$JITTER_REVERT:src/backoff.py")\` at the removal — the removal restored the pre-jitter blob
  exactly ($(same "$JITTER_REVERT:src/backoff.py" "$JITTER^:src/backoff.py")), and only the double-revert's comment moved it since

## Layer 7 — the draft notes against the tagged trees

The 1.10.0 section of \`CHANGELOG.md\` at HEAD:

\`\`\`
$(git show HEAD:CHANGELOG.md | awk '/^## 1\.10\.0/{f=1} f&&/^## 1\.9\.1/{exit} f')
\`\`\`

- bullet 1, jitter: \`grep -c random\` on \`v1.10.0:src/backoff.py\` -> $(git show v1.10.0:src/backoff.py | grep -c random || true). **MISMATCH.**
  The section was written by \`$(short "$(git rev-list -1 --grep='changelog for 1.10.0' HEAD)")\` on
  $(git log -1 --format='%ad' --date=short "$(git rev-list -1 --grep='changelog for 1.10.0' HEAD)"), after the removal on $(git log -1 --format='%ad' --date=short "$JITTER_REVERT").
- bullet 2, "warms to the configured target": \`grep -c 'def start'\` on
  \`v1.10.0:src/pool.py\` -> $(haspw v1.10.0), and \`grep -c warm_target\` -> $(git show v1.10.0:src/pool.py | grep -c warm_target || true). **MISMATCH** — at that
  tag the pool does not warm at all, and the configured-target implementation
  \`$(short "$PREWARM_3")\` lands after the tag and first ships in v1.11.0.
- bullet 3, override file: \`grep -c OVERRIDE_FILE\` on \`v1.10.0:src/config.py\` -> $(git show v1.10.0:src/config.py | grep -c OVERRIDE_FILE || true). **MATCH.**
- bullet 4, runbook checklist: \`grep -c 'Upstream recovery'\` on \`v1.10.0:docs/runbook.md\` -> $(git show v1.10.0:docs/runbook.md | grep -c 'Upstream recovery' || true). **MATCH.**

The 1.11.0 section at HEAD:

\`\`\`
$(git show HEAD:CHANGELOG.md | awk '/^## 1\.11\.0/{f=1} f&&/^## 1\.10\.0/{exit} f')
\`\`\`

- bullet 1, single-writer mode: added by \`$(short "$DECOY")\`, tags containing it -> \`$(git tag --contains "$DECOY" | tr '\n' ' ')\`. **MATCH**, but see the decoy section.
- bullet 2, resolved shard: introduced by \`$(short "$API_SHARD")\` on
  $(git log -1 --format='%ad' --date=short "$API_SHARD"). Presence of \`def resolved_shard\` by tag:
$(for t in $(git tag | sort -V); do printf '    - `%s` -> %s\n' "$t" "$(git show "$t:src/api.py" | grep -c 'def resolved_shard' || true)"; done)
  First release carrying it is \`$(git tag --contains "$API_SHARD" | grep '^v' | sort -V | head -1)\`, not 1.11.0. **MISATTRIBUTED.**
- bullet 3, pool metrics on the health endpoint: the only commit that mentions
  metrics is \`$(short "$METRICS_SUBJECT")\` ("$(git log -1 --format='%s' "$METRICS_SUBJECT")"), whose diff is
  \`$(git diff --numstat "$METRICS_SUBJECT^" "$METRICS_SUBJECT")\` and adds only a TODO comment:

\`\`\`
$(git show --format='' "$METRICS_SUBJECT" | grep '^+' | grep -v '^+++' | sed 's/^/  /')
\`\`\`

  \`grep -ci 'gauge\|metric'\` on \`HEAD:src/api.py\` -> $(git show HEAD:src/api.py | grep -ci 'gauge\|metric' || true), all of it comment text; there is no
  metrics export at any tag. **MISMATCH, supported only by a commit subject.**

## Layer 8 — the decoy: a "Revert" subject that is not a revert

\`git show --stat --format='%H%n%an%n%ad%n%s%n%n%b' --date=short $(short "$DECOY")\`:

\`\`\`
$(git show --stat --format='%H%n%an%n%ad%n%s%n%n%b' --date=short "$DECOY" | head -30)
\`\`\`

- \`git diff --numstat $(short "$DECOY")^ $(short "$DECOY")\` -> \`$(git diff --numstat "$DECOY^" "$DECOY")\`
  — **insertions only, zero deletions**.
- it adds a new class, \`$(git show "$DECOY" | grep '^+class' | sed 's/^+//')\`, to the shard module.
- nothing it could be undoing ever existed:
  \`git log --all --format='%h %s' -i --grep='single writer'\` ->
  \`$(git log --all --format='%h %s' -i --grep='single writer' | tr '\n' ';')\`
- tags containing it: \`$(git tag --contains "$DECOY" | tr '\n' ' ')\`
- so it is a **feature addition whose subject happens to begin with the word
  "Revert"** ("Revert to X" in the sense of "go back to X"). It must not be
  reported as part of any churn sequence.

## Quick index of the SHAs a claim may reference

| short | full | role |
|---|---|---|
| \`$(short "$PREWARM_1")\` | \`$PREWARM_1\` | pre-warm landing 1, on \`feature/prewarm\`, warms max_size |
| \`$(short "$MERGE_PREWARM")\` | \`$MERGE_PREWARM\` | merge that brought landing 1 to main |
| \`$(short "$REVERT_1")\` | \`$REVERT_1\` | removal 1, a true revert |
| \`$(short "$WARM_KNOB")\` | \`$WARM_KNOB\` | POOL_WARM_TARGET knob |
| \`$(short "$PREWARM_2")\` | \`$PREWARM_2\` | landing 2, same subject, lying cherry-pick trailer, warms min_size |
| \`$(short "$PREWARM_REMOVED_2")\` | \`$PREWARM_REMOVED_2\` | removal 2, subject says "simplify" |
| \`$(short "$PREWARM_3")\` | \`$PREWARM_3\` | landing 3, configured warm target |
| \`$(short "$HOTFIX_BRANCH")\` | \`$HOTFIX_BRANCH\` | hotfix on the 1.9.1 branch |
| \`$(short "$HOTFIX_MAIN")\` | \`$HOTFIX_MAIN\` | same hotfix forward-ported to main |
| \`$(short "$RENAME")\` | \`$RENAME\` | src/retry.py -> src/backoff.py |
| \`$(short "$JITTER")\` | \`$JITTER\` | jitter landed |
| \`$(short "$JITTER_REVERT")\` | \`$JITTER_REVERT\` | jitter removed, never restored |
| \`$(short "$JITTER_REREVERT")\` | \`$JITTER_REREVERT\` | "Revert of the revert" that restores nothing |
| \`$(short "$API_SHARD")\` | \`$API_SHARD\` | resolved_shard(), miscredited to 1.11.0 |
| \`$(short "$METRICS_SUBJECT")\` | \`$METRICS_SUBJECT\` | metrics subject with no metrics |
| \`$(short "$DECOY")\` | \`$DECOY\` | decoy: "Revert to a single writer per shard" |
| \`$(short HEAD)\` | \`$HEAD_SHA\` | HEAD / pinned branch tip |
HDR
} > "$HERE/GROUND_TRUTH.md"

cd "$HERE"
echo "--- artefact size ---"
wc -c pipeline-svc.bundle GROUND_TRUTH.md
echo "--- pinned SHA for environment/Dockerfile ---"
echo "$HEAD_SHA"
echo "--- assertions for environment/Dockerfile ---"
cd "$CLONE"
echo "rev-list --count HEAD = $(git rev-list --count HEAD)"
echo "tag count            = $(git tag | wc -l | tr -d ' ')"
cd "$HERE"
rm -rf "$WORK"
