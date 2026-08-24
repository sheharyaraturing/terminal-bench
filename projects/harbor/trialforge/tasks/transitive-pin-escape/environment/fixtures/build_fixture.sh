#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# build_fixture.sh — transitive-pin-escape
#
# Emits, into the directory this script lives in:
#   metrics-etl.bundle    a full-history git bundle (never --depth 1) of a
#                         synthetic 52-commit Python service repository with
#                         eight lightweight release tags, a requirements.txt, a
#                         constraints.txt, a lockfile that exists for exactly
#                         one release, and a per-release resolved-dependency
#                         audit snapshot at build/sbom.txt.
#   GROUND_TRUTH.md       written by the read-back stage at the bottom of this
#                         file, which CLONES THE BUNDLE into a scratch directory
#                         and runs the same git commands an agent would run.
#
# DETERMINISM: commit SHAs hash content, message, author, committer and BOTH
# timestamps, so every one of those is pinned here:
#   * GIT_AUTHOR_NAME / GIT_AUTHOR_EMAIL / GIT_COMMITTER_NAME /
#     GIT_COMMITTER_EMAIL are exported once, below.
#   * GIT_AUTHOR_DATE and GIT_COMMITTER_DATE are both set, per commit, to a
#     value derived arithmetically from the commit index (raw `@<epoch> +0000`
#     form, so no locale or timezone can leak in).
#   * tags are LIGHTWEIGHT (`git tag <name>`), not annotated, so no tagger
#     identity or tagger date enters any object hash.
#   * `git commit` runs with --no-gpg-sign and a scratch HOME, an empty
#     GIT_CONFIG_GLOBAL and GIT_CONFIG_SYSTEM=/dev/null, so no ambient user
#     config participates.
#   * every generated file is written by an explicit heredoc or by a loop over a
#     fixed, sorted list — no directory iteration, no RNG, no `date`.
# A re-run therefore reproduces every SHA. Verify with the read-back output.
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
export GIT_AUTHOR_NAME="Tomas Berglund"
export GIT_AUTHOR_EMAIL="tomas.berglund@example.invalid"
export GIT_COMMITTER_NAME="Tomas Berglund"
export GIT_COMMITTER_EMAIL="tomas.berglund@example.invalid"
export TZ=UTC
export LC_ALL=C

REPO="$WORK/metrics-etl"
mkdir -p "$REPO/src" "$REPO/tests" "$REPO/build" "$REPO/docs/incidents"
cd "$REPO"
git init -q -b main .

BASE_TS=1704704400          # 2024-01-08T09:00:00Z
i=0
cm() {                      # cm "<subject>" ["<body>"]
  i=$((i + 1))
  local ts=$(( BASE_TS + (i - 1) * 345600 + (i % 5) * 3600 ))
  export GIT_AUTHOR_DATE="@${ts} +0000"
  export GIT_COMMITTER_DATE="@${ts} +0000"
  git add -A
  if [ "$#" -ge 2 ]; then
    git commit -q --no-gpg-sign -m "$1" -m "$2"
  else
    git commit -q --no-gpg-sign -m "$1"
  fi
  printf '%3d %s %s\n' "$i" "$(git rev-parse --short=12 HEAD)" "$1" >> "$WORK/plan.txt"
}
al() { printf '%s\n' "$2" >> "$1"; }        # append a line

# ═══════════════════════════════════════════════════════════════════════════
#  Dependency-set snapshots
#
#  build/sbom.txt is a pip-compile-shaped record of what a release ACTUALLY
#  resolved to, annotated with each package's resolution parents. It is written
#  by the release job AFTER install; nothing installs from it. That distinction
#  is what makes the escape possible: requirements.txt and constraints.txt say
#  what was asked for, sbom.txt says what arrived.
# ═══════════════════════════════════════════════════════════════════════════

via_for() {                 # resolution parents, one per line; empty = direct
  case "$1" in
    aiobotocore)        printf 's3fs\n' ;;
    aiohttp)            printf 'aiobotocore\n' ;;
    botocore)           printf 'aiobotocore\ns3fs\n' ;;
    certifi)            printf 'requests\n' ;;
    charset-normalizer) printf 'requests\n' ;;
    fsspec)             printf 's3fs\n' ;;
    idna)               printf 'requests\nyarl\n' ;;
    numpy)              printf 'pandas\npyarrow\n' ;;
    python-dateutil)    printf 'botocore\npandas\n' ;;
    pytz)               printf 'pandas\n' ;;
    six)                printf 'python-dateutil\n' ;;
    urllib3)            printf 'botocore\nrequests\n' ;;
    wrapt)              printf 'aiobotocore\n' ;;
    yarl)               printf 'aiohttp\n' ;;
    *)                  printf '' ;;
  esac
}

write_sbom() {              # write_sbom <release> <pkg==ver> ...
  local rel="$1"; shift
  {
    echo "# Resolved dependency set, as installed."
    echo "#"
    echo "# Written by the release job after \`make install\` succeeds, from"
    echo "# \`pip freeze\` output annotated with each package's resolution"
    echo "# parents. This file is a RECORD, not an input: nothing installs from"
    echo "# it. See build/README.md."
    echo "#"
    echo "# release: $rel"
    echo
    local spec pkg parents n
    for spec in "$@"; do
      pkg="${spec%%==*}"
      echo "$spec"
      mapfile -t parents < <(via_for "$pkg")
      n="${#parents[@]}"
      if [ "$n" -eq 0 ]; then
        echo "    # via -r requirements.txt"
      elif [ "$n" -eq 1 ]; then
        echo "    # via ${parents[0]}"
      else
        echo "    # via"
        for p in "${parents[@]}"; do echo "    #   $p"; done
      fi
    done
  } > build/sbom.txt
}

# Each release's resolved set. Sorted, so the audit diff between two releases is
# exactly the set of packages whose version moved.
#
# The one that matters: botocore is 1.34.x through 2.9.0 and 1.35.x from 2.10.0.
# Between 2.9.0 and 2.10.0 exactly four packages move — botocore, certifi,
# charset-normalizer and idna — and only botocore is on the S3 write path.
R240="aiobotocore==2.11.2 aiohttp==3.9.3 botocore==1.34.34 certifi==2024.2.2 charset-normalizer==3.3.2 click==8.1.7 fsspec==2024.2.0 idna==3.6 numpy==1.26.4 pandas==2.1.4 pyarrow==14.0.2 python-dateutil==2.8.2 pytz==2024.1 requests==2.31.0 s3fs==2024.2.0 six==1.16.0 urllib3==1.26.18 wrapt==1.16.0 yarl==1.9.4"
R250="aiobotocore==2.11.2 aiohttp==3.9.3 botocore==1.34.39 certifi==2024.2.2 charset-normalizer==3.3.2 click==8.1.7 fsspec==2024.2.0 idna==3.6 numpy==1.26.4 pandas==2.1.4 pyarrow==14.0.2 python-dateutil==2.8.2 pytz==2024.1 requests==2.31.0 s3fs==2024.2.0 six==1.16.0 urllib3==1.26.18 wrapt==1.16.0 yarl==1.9.4"
R260="aiobotocore==2.12.1 aiohttp==3.9.3 botocore==1.34.44 certifi==2024.2.2 charset-normalizer==3.3.2 click==8.1.7 fsspec==2024.3.1 idna==3.6 numpy==1.26.4 pandas==2.1.4 pyarrow==14.0.2 python-dateutil==2.8.2 pytz==2024.1 requests==2.31.0 s3fs==2024.3.1 six==1.16.0 urllib3==1.26.18 wrapt==1.16.0 yarl==1.9.4"
R270="aiobotocore==2.12.1 aiohttp==3.9.3 botocore==1.34.48 certifi==2024.2.2 charset-normalizer==3.3.2 click==8.1.7 fsspec==2024.3.1 idna==3.6 numpy==1.26.4 pandas==2.1.4 pyarrow==15.0.2 python-dateutil==2.8.2 pytz==2024.1 requests==2.31.0 s3fs==2024.3.1 six==1.16.0 urllib3==1.26.18 wrapt==1.16.0 yarl==1.9.4"
R280="aiobotocore==2.12.1 aiohttp==3.9.3 botocore==1.34.51 certifi==2024.2.2 charset-normalizer==3.3.2 click==8.1.7 fsspec==2024.3.1 idna==3.6 numpy==1.26.4 pandas==2.1.4 pyarrow==15.0.2 python-dateutil==2.8.2 pytz==2024.1 requests==2.31.0 s3fs==2024.3.1 six==1.16.0 urllib3==1.26.18 wrapt==1.16.0 yarl==1.9.4"
R290="aiobotocore==2.12.3 aiohttp==3.9.5 botocore==1.34.88 certifi==2024.2.2 charset-normalizer==3.3.2 click==8.1.7 fsspec==2024.5.0 idna==3.6 numpy==1.26.4 pandas==2.2.2 pyarrow==16.1.0 python-dateutil==2.9.0 pytz==2024.1 requests==2.31.0 s3fs==2024.5.0 six==1.16.0 urllib3==1.26.18 wrapt==1.16.0 yarl==1.9.4"
R2100="aiobotocore==2.12.3 aiohttp==3.9.5 botocore==1.35.14 certifi==2024.7.4 charset-normalizer==3.3.4 click==8.1.7 fsspec==2024.5.0 idna==3.7 numpy==1.26.4 pandas==2.2.2 pyarrow==16.1.0 python-dateutil==2.9.0 pytz==2024.1 requests==2.31.0 s3fs==2024.5.0 six==1.16.0 urllib3==1.26.18 wrapt==1.16.0 yarl==1.9.4"
R2110="aiobotocore==2.15.1 aiohttp==3.10.5 botocore==1.35.29 certifi==2024.7.4 charset-normalizer==3.3.4 click==8.1.7 fsspec==2024.6.1 idna==3.7 numpy==1.26.4 pandas==2.2.2 pyarrow==17.0.0 python-dateutil==2.9.0 pytz==2024.1 requests==2.31.0 s3fs==2024.6.1 six==1.16.0 urllib3==1.26.18 wrapt==1.16.0 yarl==1.9.4"

# ── requirements.txt revisions ──────────────────────────────────────────────
# Five direct requirements. Nothing here ever names botocore.
reqs_pinned() { cat > requirements.txt <<'EOF'
# Direct requirements for metrics-etl.
# Installed with:  pip install -r requirements.txt -c constraints.txt
click==8.1.7
pandas==2.1.4
pyarrow==14.0.2
requests==2.31.0
s3fs==2024.2.0
EOF
}

# The Layer-1 finding: one direct pin loosened from == to a range.
reqs_loose() { cat > requirements.txt <<'EOF'
# Direct requirements for metrics-etl.
# Installed with:  pip install -r requirements.txt -c constraints.txt
click==8.1.7
pandas>=2.1,<3
pyarrow==15.0.2
requests==2.31.0
s3fs==2024.3.1
EOF
}

# ── constraints.txt revisions ───────────────────────────────────────────────
# Four transitive pins. Nothing here ever names botocore either.
cons_v0() { cat > constraints.txt <<'EOF'
urllib3==1.26.18
numpy==1.26.4
six==1.16.0
pytz==2024.1
EOF
}

# The DECOY: sorted, commented, spacing normalised. No version changes at all.
cons_tidy() { cat > constraints.txt <<'EOF'
# Transitive constraints. Sorted; keep it that way so the audit diff is
# readable. Applied with -c on every install.
#
# urllib3 is held on the 1.26 series because the vendored TLS shim in our
# base image has not been rebuilt against 2.x yet.
numpy == 1.26.4
pytz == 2024.1
six == 1.16.0
urllib3 == 1.26.18
EOF
}

# ── the lockfile that exists for exactly one release ────────────────────────
write_lock() {              # write_lock <pkg==ver> ...
  {
    echo "# Fully resolved lockfile. Generated with:"
    echo "#   pip-compile --generate-hashes-off --output-file requirements.lock \\"
    echo "#       requirements.txt"
    echo "# Every package is pinned, including the ones nothing asks for"
    echo "# directly. Install with:  pip install -r requirements.lock"
    echo
    local spec
    for spec in "$@"; do echo "$spec"; done
  } > requirements.lock
}

# ── Makefile revisions ──────────────────────────────────────────────────────
mk_reqs() { cat > Makefile <<'EOF'
.PHONY: install test export

install:
	pip install -r requirements.txt -c constraints.txt

test:
	pytest -q

export:
	python -m src.cli export
EOF
}

mk_lock() { cat > Makefile <<'EOF'
.PHONY: install test export lock

install:
	pip install -r requirements.lock

lock:
	pip-compile --output-file requirements.lock requirements.txt

test:
	pytest -q

export:
	python -m src.cli export
EOF
}

# ── CHANGELOG sections ──────────────────────────────────────────────────────
cl_2_4_0() { cat <<'EOF'
## 2.4.0 - 2024-02-01

- First release out of the monolith: CLI, frame normaliser, S3 parquet sink.
- Release job records the resolved dependency set for every build.
EOF
}
cl_2_5_0() { cat <<'EOF'
## 2.5.0 - 2024-02-25

- `--partition-by` on the export command.
- Timestamp columns are coerced to UTC before write.
EOF
}
cl_2_6_0() { cat <<'EOF'
## 2.6.0 - 2024-03-16

- Multipart completion is retried on a transient failure.
- README section on running an export by hand.
EOF
}
cl_2_7_0() { cat <<'EOF'
## 2.7.0 - 2024-04-05

- All-null columns are dropped before write.
- `METRICS_ETL_PROFILE` selects the credential profile.
EOF
}
cl_2_8_0() { cat <<'EOF'
## 2.8.0 - 2024-05-03

- Object keys carry the run id.
- Column order is stable across runs.
- Builds install from a fully resolved lockfile, so two builds of the same
  commit get the same dependency versions.
EOF
}
cl_2_9_0() { cat <<'EOF'
## 2.9.0 - 2024-06-04

- Relax the pandas pin so the 2.2 copy-on-write path can be picked up.
- Frame normaliser uses copy-on-write, which halves peak memory on the
  wide rollups.
EOF
}
cl_2_10_0() { cat <<'EOF'
## 2.10.0 - 2024-06-28

- `--max-rows` caps a single export.
- Faster groupby on the rollup path.
EOF
}
cl_2_11_0() { cat <<'EOF'
## 2.11.0 - 2024-07-22

- The multipart completion call is guarded and reports the object key.
- Schema lookups are memoised.
EOF
}
write_changelog() {          # args: version slugs, newest first
  {
    echo "# Changelog"
    echo
    echo "Notable changes to metrics-etl. Newest release first."
    echo
    for v in "$@"; do "cl_$v"; echo; done
  } > CHANGELOG.md
}

# ═══════════════════════════════════════════════════════════════════════════
#  52 commits
# ═══════════════════════════════════════════════════════════════════════════

# 1
cat > README.md <<'EOF'
# metrics-etl

Nightly rollup of the metrics warehouse into partitioned parquet on S3.

    make install
    make export

`requirements.txt` holds the direct requirements and `constraints.txt` the
transitive pins we have a reason to hold. Release history is in CHANGELOG.md.
EOF
cat > src/cli.py <<'EOF'
"""Command-line entry point."""

VERSION = "2.4.0"


def main(argv=None):
    from src.frame import normalise
    from src.sink_s3 import ParquetSink

    sink = ParquetSink()
    return sink.write(normalise([]))
EOF
reqs_pinned
cons_v0
mk_reqs
cm "Initial import of metrics-etl"

# 2
cat > src/frame.py <<'EOF'
"""Dataframe normalisation."""

import pandas as pd


def normalise(rows):
    """Rows in, a canonical frame out."""
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame = frame.rename(columns=str.lower)
    return frame.reset_index(drop=True)
EOF
cm "frame: add the dataframe normaliser"

# 3
cat > tests/test_frame.py <<'EOF'
from src.frame import normalise


def test_normalise_lowercases_columns():
    frame = normalise([{"Metric": "a", "Value": 1}])
    assert list(frame.columns) == ["metric", "value"]
EOF
cm "tests: cover the frame normaliser"

# 4
cat > src/sink_s3.py <<'EOF'
"""Partitioned parquet sink on S3.

The bucket is reached through s3fs, which brings its own AWS client stack; we
never import that stack directly.
"""

import s3fs


class ParquetSink:
    def __init__(self, bucket="metrics-rollups", part_bytes=8 * 1024 * 1024):
        self.bucket = bucket
        self.part_bytes = part_bytes
        self.fs = s3fs.S3FileSystem()

    def _client(self):
        return self.fs.s3

    def begin(self, key):
        return self._client().create_multipart_upload(Bucket=self.bucket, Key=key)

    def complete(self, key, upload_id, parts):
        return self._client().complete_multipart_upload(
            Bucket=self.bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )

    def write(self, frame):
        return len(frame)
EOF
cm "sink: add the partitioned parquet sink"

# 5
cat > build/README.md <<'EOF'
# build/

`sbom.txt` is written by the release job **after** `make install` succeeds. It
is `pip freeze` output annotated with each package's resolution parents, so it
records what the release actually resolved to, including packages nothing in
the repository asks for by name.

Nothing installs from `sbom.txt`. It is an audit record only. If you want a
build to be reproducible you need a lockfile, not this.
EOF
cm "build: describe the resolved-set audit snapshot"

# 6
write_changelog 2_4_0
cm "docs: add a changelog for 2.4.0"

# 7  <<< tag v2.4.0
write_sbom "2.4.0" $R240
cm "release: 2.4.0"
git tag v2.4.0

# 8
al src/cli.py ""
al src/cli.py "def dry_run(argv=None):"
al src/cli.py "    return {\"dry_run\": True}"
cm "cli: add a --dry-run mode"

# 9
al src/frame.py ""
al src/frame.py "def to_utc(frame, column):"
al src/frame.py "    frame[column] = pd.to_datetime(frame[column], utc=True)"
al src/frame.py "    return frame"
cm "frame: coerce timestamp columns to UTC"

# 10
al src/cli.py ""
al src/cli.py "def partition_by(frame, keys):"
al src/cli.py "    return [k for k in keys if k in frame.columns]"
cm "cli: add a --partition-by flag"

# 11
al tests/test_frame.py ""
al tests/test_frame.py "def test_to_utc_is_tz_aware():"
al tests/test_frame.py "    import pandas as pd"
al tests/test_frame.py "    frame = pd.DataFrame({\"ts\": [\"2024-01-01\"]})"
al tests/test_frame.py "    from src.frame import to_utc"
al tests/test_frame.py "    assert to_utc(frame, \"ts\")[\"ts\"].dt.tz is not None"
cm "tests: cover the UTC coercion"

# 12
write_changelog 2_5_0 2_4_0
cm "docs: changelog for 2.5.0"

# 13  <<< tag v2.5.0
write_sbom "2.5.0" $R250
sed -i 's/^VERSION = .*/VERSION = "2.5.0"/' src/cli.py
cm "release: 2.5.0"
git tag v2.5.0

# 14
al src/sink_s3.py ""
al src/sink_s3.py "    def complete_with_retry(self, key, upload_id, parts, attempts=3):"
al src/sink_s3.py "        last = None"
al src/sink_s3.py "        for _ in range(attempts):"
al src/sink_s3.py "            try:"
al src/sink_s3.py "                return self.complete(key, upload_id, parts)"
al src/sink_s3.py "            except OSError as exc:"
al src/sink_s3.py "                last = exc"
al src/sink_s3.py "        raise last"
cm "sink: retry the multipart completion on a transient failure"

# 15
al README.md ""
al README.md "## Running an export by hand"
al README.md ""
al README.md "    python -m src.cli export --partition-by day"
cm "docs: README section on running an export by hand"

# 16
al tests/test_frame.py ""
al tests/test_frame.py "def test_partition_by_ignores_unknown_keys():"
al tests/test_frame.py "    import pandas as pd"
al tests/test_frame.py "    from src.cli import partition_by"
al tests/test_frame.py "    frame = pd.DataFrame({\"day\": [1]})"
al tests/test_frame.py "    assert partition_by(frame, [\"day\", \"hour\"]) == [\"day\"]"
cm "tests: cover the partition-by flag"

# 17
write_changelog 2_6_0 2_5_0 2_4_0
cm "docs: changelog for 2.6.0"

# 18  <<< tag v2.6.0
write_sbom "2.6.0" $R260
sed -i 's/^VERSION = .*/VERSION = "2.6.0"/' src/cli.py
sed -i 's/^s3fs==.*/s3fs==2024.3.1/' requirements.txt
cm "release: 2.6.0"
git tag v2.6.0

# 19
al src/frame.py ""
al src/frame.py "def drop_all_null(frame):"
al src/frame.py "    return frame.dropna(axis=1, how=\"all\")"
cm "frame: drop all-null columns before write"

# 20
al src/cli.py ""
al src/cli.py "def credential_profile(env):"
al src/cli.py "    return env.get(\"METRICS_ETL_PROFILE\", \"default\")"
cm "cli: honour METRICS_ETL_PROFILE"

# 21
al tests/test_frame.py ""
al tests/test_frame.py "def test_drop_all_null_removes_empty_columns():"
al tests/test_frame.py "    import pandas as pd"
al tests/test_frame.py "    from src.frame import drop_all_null"
al tests/test_frame.py "    frame = pd.DataFrame({\"a\": [1], \"b\": [None]})"
al tests/test_frame.py "    assert list(drop_all_null(frame).columns) == [\"a\"]"
cm "tests: cover the all-null column drop"

# 22
write_changelog 2_7_0 2_6_0 2_5_0 2_4_0
cm "docs: changelog for 2.7.0"

# 23  <<< tag v2.7.0
write_sbom "2.7.0" $R270
sed -i 's/^VERSION = .*/VERSION = "2.7.0"/' src/cli.py
sed -i 's/^pyarrow==.*/pyarrow==15.0.2/' requirements.txt
cm "release: 2.7.0"
git tag v2.7.0

# 24
al src/sink_s3.py ""
al src/sink_s3.py "    def object_key(self, run_id, partition):"
al src/sink_s3.py "        return f\"rollups/{partition}/{run_id}.parquet\""
cm "sink: put the run id in the object key"

# 25
al src/frame.py ""
al src/frame.py "def stable_columns(frame):"
al src/frame.py "    return frame[sorted(frame.columns)]"
cm "frame: keep column order stable across runs"

# 26
al tests/test_frame.py ""
al tests/test_frame.py "def test_stable_columns_is_sorted():"
al tests/test_frame.py "    import pandas as pd"
al tests/test_frame.py "    from src.frame import stable_columns"
al tests/test_frame.py "    frame = pd.DataFrame({\"b\": [1], \"a\": [2]})"
al tests/test_frame.py "    assert list(stable_columns(frame).columns) == [\"a\", \"b\"]"
cm "tests: cover stable column order"

# 27  <<< LOCKFILE ADDED — the only release that will ship with it is 2.8.0
write_lock $R280
mk_lock
cm "build: install from a fully resolved lockfile" \
   "Two builds of the same commit have been picking up different versions of
things we never named, because requirements.txt only constrains what we ask for
directly. Commit the resolved set and install from it. Refresh with \`make lock\`
when a direct requirement moves."

# 28
al src/cli.py ""
al src/cli.py "def resolved_set(path=\"build/sbom.txt\"):"
al src/cli.py "    with open(path) as handle:"
al src/cli.py "        return [l.strip() for l in handle if l.strip() and not l.startswith(\"#\")]"
cm "cli: report the recorded dependency set on --version"

# 29
write_changelog 2_8_0 2_7_0 2_6_0 2_5_0 2_4_0
cm "docs: changelog for 2.8.0"

# 30  <<< tag v2.8.0  — the one release with a hard pin on everything
write_sbom "2.8.0" $R280
sed -i 's/^VERSION = .*/VERSION = "2.8.0"/' src/cli.py
cm "release: 2.8.0"
git tag v2.8.0

# 31  <<< LOCKFILE DELETED — the escape opens here
rm requirements.lock
mk_reqs
cm "build: stop installing from the lockfile" \
   "The lockfile has been three weeks stale for most of this cycle and the
refresh job keeps losing a race with the security-update bot, so half the CI
runs fail on a hash mismatch rather than on anything real. Going back to
requirements.txt with constraints.txt applied until somebody owns the refresh."

# 32
al tests/test_frame.py ""
al tests/test_frame.py "def test_normalise_of_empty_is_empty():"
al tests/test_frame.py "    assert normalise([]).empty"
cm "tests: trim the frame fixtures"

# 33  <<< DECOY — a pin edit that changes no version
cons_tidy
cm "deps: tidy up constraints.txt" \
   "Sorting the constraints file and writing down why urllib3 is held, because
every time somebody new looks at it they try to bump it. Same four constraints,
same four versions."

# 34  <<< LAYER 1 — the direct pin that was loosened
reqs_loose
cm "deps: loosen the pandas pin" \
   "The copy-on-write work needs pandas 2.2 and we are pinned to 2.1.4, so the
pin has to come off before the rollup change can land. Range rather than a
straight bump so we are not chasing patch releases every fortnight."

# 35
cat > src/frame.py <<'EOF'
"""Dataframe normalisation."""

import pandas as pd

pd.options.mode.copy_on_write = True


def normalise(rows):
    """Rows in, a canonical frame out."""
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame = frame.rename(columns=str.lower)
    return frame.reset_index(drop=True)


def to_utc(frame, column):
    frame[column] = pd.to_datetime(frame[column], utc=True)
    return frame


def drop_all_null(frame):
    return frame.dropna(axis=1, how="all")


def stable_columns(frame):
    return frame[sorted(frame.columns)]
EOF
cm "frame: switch the rollup path to copy-on-write"

# 36
al tests/test_frame.py ""
al tests/test_frame.py "def test_copy_on_write_is_enabled():"
al tests/test_frame.py "    import pandas as pd"
al tests/test_frame.py "    import src.frame  # noqa: F401"
al tests/test_frame.py "    assert pd.options.mode.copy_on_write is True"
cm "tests: cover the copy-on-write switch"

# 37
write_changelog 2_9_0 2_8_0 2_7_0 2_6_0 2_5_0 2_4_0
cm "docs: changelog for 2.9.0"

# 38  <<< tag v2.9.0 — first release with no lockfile. Builds clean anyway.
write_sbom "2.9.0" $R290
sed -i 's/^VERSION = .*/VERSION = "2.9.0"/' src/cli.py
sed -i 's/^pyarrow==.*/pyarrow==16.1.0/' requirements.txt
sed -i 's/^s3fs==.*/s3fs==2024.5.0/' requirements.txt
cm "release: 2.9.0"
git tag v2.9.0

# 39
al src/cli.py ""
al src/cli.py "def max_rows(argv, default=None):"
al src/cli.py "    return default"
cm "cli: add --max-rows"

# 40
al src/cli.py ""
al src/cli.py "def quiet(argv):"
al src/cli.py "    return \"--quiet\" in (argv or [])"
cm "cli: add a --quiet flag"

# 41
al src/frame.py ""
al src/frame.py "def rollup(frame, keys, column):"
al src/frame.py "    return frame.groupby(keys, observed=True, sort=False)[column].sum()"
cm "frame: faster groupby on the rollup path"

# 42
al tests/test_frame.py ""
al tests/test_frame.py "def test_max_rows_defaults_to_none():"
al tests/test_frame.py "    from src.cli import max_rows"
al tests/test_frame.py "    assert max_rows([]) is None"
cm "tests: cover --max-rows"

# 43
write_changelog 2_10_0 2_9_0 2_8_0 2_7_0 2_6_0 2_5_0 2_4_0
cm "docs: changelog for 2.10.0"

# 44  <<< tag v2.10.0 — the first failing release
write_sbom "2.10.0" $R2100
sed -i 's/^VERSION = .*/VERSION = "2.10.0"/' src/cli.py
cm "release: 2.10.0"
git tag v2.10.0

# 45
al src/cli.py ""
al src/cli.py "def usage():"
al src/cli.py "    return \"metrics-etl export [--partition-by KEY] [--max-rows N] [--quiet]\""
cm "cli: tidy up the help text"

# 46  <<< the incident record
cat > docs/incidents/2024-07-nightly-export.md <<'EOF'
# Nightly export failing since the 2.10.0 rollout

## Symptom

Every nightly run since the 2.10.0 workers went out dies at the upload step:

    TypeError: complete_multipart_upload() got an unexpected keyword argument
    'ChecksumCRC32'

raised from `ParquetSink.complete()` in `src/sink_s3.py`, inside the AWS
client call. Nothing is written; the run exits non-zero and the rollup
partition is left missing.

## What we have ruled out

- **Input data.** The same input replayed on a worker still on 2.10.0's
  predecessor completes and writes the partition.
- **Our code.** `src/sink_s3.py` has not been touched since 2.8.0.
- **Credentials and bucket policy.** Unchanged, and a manual multipart put
  with the same role succeeds.
- **pyarrow.** The parquet bytes are produced before the upload starts and are
  byte-identical between the two workers.

## Where that leaves us

The failing call is not one of ours and the keyword in the error is not one we
pass, so something in the installed dependency set moved between the last good
release and 2.10.0. Neither `requirements.txt` nor `constraints.txt` changed
between those two tags.

Needs somebody to work out which package moved, how it got in, and why nothing
stopped it.
EOF
cm "docs: record the nightly export failure"

# 47
al src/sink_s3.py ""
al src/sink_s3.py "    def complete_guarded(self, key, upload_id, parts):"
al src/sink_s3.py "        try:"
al src/sink_s3.py "            return self.complete(key, upload_id, parts)"
al src/sink_s3.py "        except TypeError as exc:"
al src/sink_s3.py "            raise RuntimeError(f\"multipart completion rejected: {exc}\") from exc"
cm "sink: turn the completion failure into a legible error"

# 48
al src/frame.py ""
al src/frame.py "_SCHEMA_CACHE = {}"
al src/frame.py ""
al src/frame.py "def schema_for(name, loader):"
al src/frame.py "    if name not in _SCHEMA_CACHE:"
al src/frame.py "        _SCHEMA_CACHE[name] = loader(name)"
al src/frame.py "    return _SCHEMA_CACHE[name]"
cm "frame: memoise the schema lookup"

# 49
write_changelog 2_11_0 2_10_0 2_9_0 2_8_0 2_7_0 2_6_0 2_5_0 2_4_0
cm "docs: changelog for 2.11.0"

# 50  <<< tag v2.11.0 — still failing
write_sbom "2.11.0" $R2110
sed -i 's/^VERSION = .*/VERSION = "2.11.0"/' src/cli.py
sed -i 's/^pyarrow==.*/pyarrow==17.0.0/' requirements.txt
sed -i 's/^s3fs==.*/s3fs==2024.6.1/' requirements.txt
cm "release: 2.11.0"
git tag v2.11.0

# 51
al tests/test_frame.py ""
al tests/test_frame.py "def test_rollup_sums():"
al tests/test_frame.py "    import pandas as pd"
al tests/test_frame.py "    from src.frame import rollup"
al tests/test_frame.py "    frame = pd.DataFrame({\"k\": [\"a\", \"a\"], \"v\": [1, 2]})"
al tests/test_frame.py "    assert rollup(frame, [\"k\"], \"v\").loc[\"a\"] == 3"
cm "tests: cover the rollup sum"

# 52
al README.md ""
al README.md "## The audit snapshot"
al README.md ""
al README.md "Every release commit rewrites build/sbom.txt with the set that build"
al README.md "actually resolved to, annotated with what pulled each package in."
cm "docs: README note on the audit snapshot"

# ── bundle ──────────────────────────────────────────────────────────────────
git bundle create "$HERE/metrics-etl.bundle" --all
HEAD_SHA="$(git rev-parse HEAD)"
echo "HEAD = $HEAD_SHA"

# ═══════════════════════════════════════════════════════════════════════════
#  READ-BACK STAGE — clone the bundle and interrogate the clone
#
#  Everything in GROUND_TRUTH.md below is the output of git commands run
#  against a FRESH CLONE of the bundle, not against the working tree above.
# ═══════════════════════════════════════════════════════════════════════════
CLONE="$WORK/readback"
rm -rf "$CLONE"
git clone -q "$HERE/metrics-etl.bundle" "$CLONE"
cd "$CLONE"
git checkout -q -B main "$HEAD_SHA"   # bundle carries HEAD, so `main` exists already

short() { git rev-parse --short=12 "$1"; }

LOOSEN=$(git log --format='%H' --grep='^deps: loosen the pandas pin$' | tail -1)
DECOY=$(git log --format='%H'  --grep='^deps: tidy up constraints.txt$' | tail -1)
LOCKADD=$(git log --format='%H' --grep='^build: install from a fully resolved lockfile$' | tail -1)
LOCKDEL=$(git log --format='%H' --grep='^build: stop installing from the lockfile$' | tail -1)

# The audit-snapshot comparison, done with independent code rather than by
# trusting the R2xx variables above: parse build/sbom.txt out of each tag.
cat > "$WORK/cmp.py" <<'PY'
import re, subprocess, sys

def pins(rev):
    txt = subprocess.run(["git", "show", f"{rev}:build/sbom.txt"],
                         capture_output=True, text=True, check=True).stdout
    out = {}
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9._-]+)==(.+)$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out

a, b = sys.argv[1], sys.argv[2]
pa, pb = pins(a), pins(b)
moved = sorted(k for k in pa if k in pb and pa[k] != pb[k])
print(f"packages recorded at {a}: {len(pa)}")
print(f"packages recorded at {b}: {len(pb)}")
print(f"added: {sorted(set(pb) - set(pa))}  removed: {sorted(set(pa) - set(pb))}")
print(f"version changes ({len(moved)}):")
for k in moved:
    print(f"  {k}: {pa[k]} -> {pb[k]}")
PY

vias() {   # print the `# via` block for one package at one rev
  git show "$1:build/sbom.txt" | awk -v pkg="$2" '
    $0 ~ "^"pkg"==" {show=1; print; next}
    show && /^    #/ {print; next}
    show {exit}
  '
}

{
cat <<HDR
# GROUND_TRUTH.md — transitive-pin-escape

Everything below is the **output of commands run against a fresh clone of
\`metrics-etl.bundle\`**, not against the builder's working tree. \`bash
build_fixture.sh\` rebuilds the bundle and regenerates this file, so the SHAs
below are the SHAs an agent will see.

Read-back procedure:

\`\`\`
git clone metrics-etl.bundle readback
cd readback && git checkout -B main $HEAD_SHA
\`\`\`

## Shape of the repository

- pinned branch tip (the SHA \`environment/Dockerfile\` checks out as \`main\`):
  \`$HEAD_SHA\`
- \`git cat-file -t $HEAD_SHA\` in the clone -> \`$(git cat-file -t "$HEAD_SHA")\`
- \`git rev-list --count HEAD\` -> **$(git rev-list --count HEAD)** commits, single linear branch
  (\`git rev-list --count --merges HEAD\` -> $(git rev-list --count --merges HEAD) merge commits)
- tracked files at HEAD ($(git ls-files | wc -l | tr -d ' ')):
$(git ls-files | sed 's/^/  - `/;s/$/`/')
- author on every commit: \`$(git log --format='%an <%ae>' | sort -u | tr '\n' ' ')\`
- first commit $(git log --reverse --format='%ad' --date=short | head -1), last commit $(git log -1 --format='%ad' --date=short)

### Tags carried by the bundle

\`git tag\` (git's own default ordering, which is lexical):

\`\`\`
$(git tag)
\`\`\`

Lexical order puts \`v2.10.0\` and \`v2.11.0\` **before** \`v2.4.0\`. Semantic order
is v2.4.0 < v2.5.0 < v2.6.0 < v2.7.0 < v2.8.0 < v2.9.0 < v2.10.0 < v2.11.0.
\`sort -V\` agrees with semantic order:

\`\`\`
$(git tag | sort -V)
\`\`\`

Tag -> commit:

$(for t in $(git tag | sort -V); do printf '  - `%s` -> `%s`  %s\n' "$t" "$(short "$t")" "$(git log -1 --format='%ad' --date=short "$t")"; done)

## What the two dependency input files ever contain

\`git log --format='%h %ad %s' --date=short -- requirements.txt constraints.txt requirements.lock\`:

\`\`\`
$(git log --format='%h %ad %s' --date=short -- requirements.txt constraints.txt requirements.lock)
\`\`\`

\`requirements.txt\` at HEAD:

\`\`\`
$(git show HEAD:requirements.txt)
\`\`\`

\`constraints.txt\` at HEAD:

\`\`\`
$(git show HEAD:constraints.txt)
\`\`\`

Neither file ever names botocore, at any commit:

\`\`\`
git log --all --format='%h' -- requirements.txt constraints.txt \\
  | while read c; do git show \$c:requirements.txt \$c:constraints.txt; done | grep -c botocore
-> $(for c in $(git log --format='%H' -- requirements.txt constraints.txt); do git show "$c:requirements.txt" 2>/dev/null || true; git show "$c:constraints.txt" 2>/dev/null || true; done | grep -ci botocore || true)
\`\`\`

Direct requirements at HEAD: **$(git show HEAD:requirements.txt | grep -cvE '^\s*(#|$)')**.
Constraint entries at HEAD: **$(git show HEAD:constraints.txt | grep -cvE '^\s*(#|$)')**.

## Layer 1 — the direct pin that was loosened

| field | value |
|---|---|
| full SHA | \`$LOOSEN\` |
| short | \`$(short "$LOOSEN")\` |
| date | $(git log -1 --format='%ad' --date=short "$LOOSEN") |
| subject | $(git log -1 --format='%s' "$LOOSEN") |

\`git show --format= -U0 $(short "$LOOSEN") -- requirements.txt\`:

\`\`\`
$(git show --format= -U0 "$LOOSEN" -- requirements.txt)
\`\`\`

\`git show --numstat --format= $LOOSEN\`:

\`\`\`
$(git show --numstat --format= "$LOOSEN")
\`\`\`

Commit body:

\`\`\`
$(git log -1 --format='%b' "$LOOSEN")
\`\`\`

### Which release the loosening first shipped in — the tag-ordering trap

\`git tag --contains $(short "$LOOSEN")\` prints, in git's own order:

\`\`\`
$(git tag --contains "$LOOSEN")
\`\`\`

That is **lexical**. \`sort -V\` on the same set:

\`\`\`
$(git tag --contains "$LOOSEN" | sort -V)
\`\`\`

So the first line of the naive command is \`$(git tag --contains "$LOOSEN" | head -1)\` and the correct
answer is **\`$(git tag --contains "$LOOSEN" | sort -V | head -1)\`**.

## Layer 2a — the loosened pandas pin is not the cause

pandas as RECORDED IN THE AUDIT SNAPSHOT at each release
(\`git show <tag>:build/sbom.txt | grep -A1 '^pandas=='\`):

$(for t in $(git tag | sort -V); do printf '  - `%s` -> `%s`\n' "$t" "$(git show "$t:build/sbom.txt" | grep '^pandas==' )"; done)

pandas is **identical at v2.9.0 and v2.10.0**, so the loosened pin changed
nothing across the failure boundary. It did change what shipped between v2.8.0
and v2.9.0 — and v2.9.0 built clean.

## Layer 2b — what actually moved across the failure boundary

The incident record (\`docs/incidents/2024-07-nightly-export.md\`, added by
$(short "$(git log --format='%H' --grep='^docs: record the nightly export failure$' | tail -1)")) puts the
first failing release at 2.10.0 and the last good one at its predecessor.

\`python3 cmp.py v2.9.0 v2.10.0\` — parses \`build/sbom.txt\` out of both tags
with independent code and diffs the pins:

\`\`\`
$(cd "$CLONE" && python3 "$WORK/cmp.py" v2.9.0 v2.10.0)
\`\`\`

For contrast, the same comparison one release earlier:

\`\`\`
$(cd "$CLONE" && python3 "$WORK/cmp.py" v2.8.0 v2.9.0)
\`\`\`

and one release later:

\`\`\`
$(cd "$CLONE" && python3 "$WORK/cmp.py" v2.10.0 v2.11.0)
\`\`\`

### Why botocore and not the other three

The \`# via\` annotations in the snapshot give the resolution parents. At v2.10.0:

\`\`\`
$(vias v2.10.0 botocore)
$(vias v2.10.0 certifi)
$(vias v2.10.0 charset-normalizer)
$(vias v2.10.0 idna)
\`\`\`

\`src/sink_s3.py\` imports \`s3fs\` and calls \`complete_multipart_upload\` on the
client s3fs owns; certifi, charset-normalizer and idna arrive via \`requests\`
and \`aiohttp\`/\`yarl\` and are not on that path. botocore is the only one of the
four that is.

botocore across every release:

$(for t in $(git tag | sort -V); do printf '  - `%s` -> `%s`\n' "$t" "$(git show "$t:build/sbom.txt" | grep '^botocore==' )"; done)

## Layer 2c — the lockfile that existed for exactly one release

| event | full SHA | short | date | subject |
|---|---|---|---|---|
| added | \`$LOCKADD\` | \`$(short "$LOCKADD")\` | $(git log -1 --format='%ad' --date=short "$LOCKADD") | $(git log -1 --format='%s' "$LOCKADD") |
| deleted | \`$LOCKDEL\` | \`$(short "$LOCKDEL")\` | $(git log -1 --format='%ad' --date=short "$LOCKDEL") | $(git log -1 --format='%s' "$LOCKDEL") |

\`git log --diff-filter=AD --format='%h %ad %s' --date=short -- requirements.lock\`:

\`\`\`
$(git log --diff-filter=AD --format='%h %ad %s' --date=short -- requirements.lock)
\`\`\`

**Which releases actually carry the file** (\`git cat-file -e <tag>:requirements.lock\`):

$(for t in $(git tag | sort -V); do if git cat-file -e "$t:requirements.lock" 2>/dev/null; then echo "  - \`$t\` -> requirements.lock PRESENT"; else echo "  - \`$t\` -> absent"; fi; done)

Exactly **$(n=0; for t in $(git tag); do git cat-file -e "$t:requirements.lock" 2>/dev/null && n=$((n+1)); done; echo $n)** release carries it.

Note the second trap here. \`git tag --contains $(short "$LOCKADD")\` reports four
tags, because the commit that ADDED the file is an ancestor of all of them:

\`\`\`
$(git tag --contains "$LOCKADD" | sort -V | tr '\n' ' ')
\`\`\`

Containment of the commit is not presence of the file. Only the tag between the
add and the delete has it.

botocore's pin in the lockfile, at the one release that has it:

\`\`\`
$(git show v2.8.0:requirements.lock | grep '^botocore==')
\`\`\`

Lines in the lockfile: **$(git show v2.8.0:requirements.lock | grep -cvE '^\s*(#|$)')**, versus
$(git show v2.8.0:requirements.txt | grep -cvE '^\s*(#|$)') direct requirements and
$(git show v2.8.0:constraints.txt | grep -cvE '^\s*(#|$)') constraints.

The Makefile install target follows the lockfile in and out:

\`\`\`
$(git show "$LOCKADD:Makefile" | sed -n '3,5p')
\`\`\`
\`\`\`
$(git show "$LOCKDEL:Makefile" | sed -n '3,5p')
\`\`\`

## The decoy — a pin edit that changes no version

| field | value |
|---|---|
| full SHA | \`$DECOY\` |
| short | \`$(short "$DECOY")\` |
| date | $(git log -1 --format='%ad' --date=short "$DECOY") |
| subject | $(git log -1 --format='%s' "$DECOY") |

\`git show --numstat --format= $(short "$DECOY")\`:

\`\`\`
$(git show --numstat --format= "$DECOY")
\`\`\`

\`git show --format= $(short "$DECOY")\`:

\`\`\`
$(git show --format= "$DECOY")
\`\`\`

Constraint set before and after, reduced to name==version with whitespace
stripped:

\`\`\`
before: $(git show "$DECOY^:constraints.txt" | grep -vE '^\s*(#|$)' | tr -d ' ' | sort | tr '\n' ' ')
after:  $(git show "$DECOY:constraints.txt"  | grep -vE '^\s*(#|$)' | tr -d ' ' | sort | tr '\n' ' ')
identical: $(if [ "$(git show "$DECOY^:constraints.txt" | grep -vE '^\s*(#|$)' | tr -d ' ' | sort)" = "$(git show "$DECOY:constraints.txt" | grep -vE '^\s*(#|$)' | tr -d ' ' | sort)" ]; then echo YES; else echo NO; fi)
\`\`\`

It lands two commits before the pandas loosening and reads like a dependency
change. It is not one.

## Full commit list

\`git log --format='%h %ad %s' --date=short --reverse\`:

\`\`\`
$(git log --format='%h %ad %s' --date=short --reverse)
\`\`\`
HDR
} > "$HERE/GROUND_TRUTH.md"

echo "wrote $HERE/GROUND_TRUTH.md"
cd "$HERE"
sha256sum metrics-etl.bundle GROUND_TRUTH.md
ls -l metrics-etl.bundle GROUND_TRUTH.md
rm -rf "$WORK"
