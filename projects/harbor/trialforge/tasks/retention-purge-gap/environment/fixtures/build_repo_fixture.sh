#!/bin/bash
# Build the deterministic internal retention-platform history from the pinned,
# sanitized upstream source snapshot and checked-in overlay files.
set -euo pipefail
cd "$(dirname "$0")"

upstream_sha="debde74347f4147d0d2c745b1e4d98c1c64dfa74"
upstream_tag="upstream-qumulo-filelock-debde743"
upstream_snapshot="upstream_snapshot"
output_bundle="bundles/retention-platform.bundle"
overlay="repo_overlay"

test -s "$upstream_snapshot/qfs_filelock.py"
test -s "$upstream_snapshot/LICENSE"
test -s "$upstream_snapshot/UPSTREAM_PROVENANCE.md"
test -f "$overlay/INTERNAL_FORK_NOTICE.md"

fixture_tmp="$(mktemp -d)"
trap 'rm -rf "$fixture_tmp"' EXIT
repo="$fixture_tmp/retention-platform"

git init -q --initial-branch production "$repo"
git -C "$repo" config user.name "Retention Platform Build"
git -C "$repo" config user.email "retention-platform@example.invalid"
git -C "$repo" config commit.gpgsign false

export GIT_AUTHOR_NAME="Retention Platform Build"
export GIT_AUTHOR_EMAIL="retention-platform@example.invalid"
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"

commit_at() {
  export GIT_AUTHOR_DATE="$1"
  export GIT_COMMITTER_DATE="$1"
  git -C "$repo" commit -q -m "$2"
}

cp "$upstream_snapshot/qfs_filelock.py" "$repo/qfs_filelock.py"
cp "$upstream_snapshot/LICENSE" "$repo/LICENSE"
cp "$upstream_snapshot/UPSTREAM_PROVENANCE.md" "$repo/UPSTREAM_PROVENANCE.md"
git -C "$repo" add qfs_filelock.py LICENSE UPSTREAM_PROVENANCE.md
commit_at "2025-11-30T09:00:00Z" "Import sanitized Qumulo/filelock source snapshot"
git -C "$repo" tag "$upstream_tag"

install -d "$repo/platform_retention" "$repo/policies" "$repo/reports" "$repo/deploy"
cp "$overlay/INTERNAL_FORK_NOTICE.md" "$repo/INTERNAL_FORK_NOTICE.md"
cp "$overlay/retention_README.md" "$repo/RETENTION_PLATFORM.md"
cp "$overlay/platform_retention/__init__.py" "$repo/platform_retention/__init__.py"
cp "$overlay/platform_retention/selector-v2.3.1.py" "$repo/platform_retention/selector.py"
cp "$overlay/platform_retention/hold-adapter-v1.8.1.py" "$repo/platform_retention/hold_adapter.py"
cp "$overlay/policies/RS-2025.3.md" "$repo/policies/RS-2025.3.md"
git -C "$repo" add INTERNAL_FORK_NOTICE.md RETENTION_PLATFORM.md platform_retention policies/RS-2025.3.md
commit_at "2025-12-01T09:00:00Z" "Initialize internal retention platform fork"
git -C "$repo" tag selector-v2.3.1
git -C "$repo" tag lock-adapter-v1.8.1

cp policy.md "$repo/policies/RS-2026.1.md"
git -C "$repo" add policies/RS-2026.1.md
commit_at "2026-01-15T10:30:00Z" "Put retention schedule RS-2026.1 in force"
git -C "$repo" tag RS-2026.1

cp "$overlay/platform_retention/selector-v2.4.0.py" "$repo/platform_retention/selector.py"
git -C "$repo" add platform_retention/selector.py
commit_at "2026-02-10T14:20:00Z" "Reduce selector timestamp conversion overhead"
git -C "$repo" tag selector-v2.4.0

cp "$overlay/platform_retention/hold-adapter-v1.8.2.py" "$repo/platform_retention/hold_adapter.py"
git -C "$repo" add platform_retention/hold_adapter.py
commit_at "2026-03-10T11:45:00Z" "Honor upstream recent-lock cache expiry"
git -C "$repo" tag lock-adapter-v1.8.2

cp "$overlay/policies/RS-2026.2-draft.md" "$repo/policies/RS-2026.2-draft.md"
git -C "$repo" add policies/RS-2026.2-draft.md
commit_at "2026-03-25T16:10:00Z" "Add RS-2026.2 for policy review"

cp "$overlay/deploy/production.toml" "$repo/deploy/production.toml"
git -C "$repo" add deploy/production.toml
commit_at "2026-03-28T18:00:00Z" "Freeze production purge release for April cycle"
git -C "$repo" tag prod-2026-04-01

git -C "$repo" merge-base --is-ancestor "$upstream_tag" production
test "$(git -C "$repo" rev-parse prod-2026-04-01)" = "$(git -C "$repo" rev-parse production)"
test "$(git -C "$repo" show selector-v2.4.0:platform_retention/selector.py | grep -c 'value\[:19\]')" = "1"
test "$(git -C "$repo" show lock-adapter-v1.8.1:platform_retention/hold_adapter.py | grep -c 'return storage_path in recent_locks')" = "1"
test "$(git -C "$repo" show lock-adapter-v1.8.2:platform_retention/hold_adapter.py | grep -c 'now_epoch - cached_at < cooldown_seconds')" = "1"
test "$(git -C "$repo" show "$upstream_tag":qfs_filelock.py | grep -c 'current_time - recent_locks\[full_path\].*< cooldown')" = "1"
test "$(git -C "$repo" show "$upstream_tag":UPSTREAM_PROVENANCE.md | grep -c "$upstream_sha")" = "1"
test "$(git -C "$repo" show "$upstream_tag":qfs_filelock.py | shasum -a 256 | cut -d' ' -f1)" = "92c46ee2d28537b0a338a1522784e1c75887997e6cbec03c43c3f3f04d5b1c29"
test "$(git -C "$repo" show prod-2026-04-01:deploy/production.toml | grep -c 'deployment_id = "DPL-20260401-017"')" = "1"
test "$(git -C "$repo" show prod-2026-04-01:deploy/production.toml | grep -c 'storage_lock_contract_ref = "upstream-qumulo-filelock-debde743"')" = "1"
test "$(git -C "$repo" show prod-2026-04-01:RETENTION_PLATFORM.md | grep -c 'receipt journal is append-only')" = "1"
! git -C "$repo" show prod-2026-04-01:RETENTION_PLATFORM.md | grep -q 'five-second'
test ! -e "$repo/qfs_filelock_config.ini"
test ! -e "$repo/test_qfs_filelock.sh"
test -s "$repo/LICENSE"

git -C "$repo" switch -q -c audit-review
cp "$overlay/reports/2026-Q1-regulator-return.md" "$repo/reports/2026-Q1-regulator-return.md"
git -C "$repo" add reports/2026-Q1-regulator-return.md
commit_at "2026-04-08T13:20:00Z" "Record regulator return on Q1 retention evidence"
test "$(git -C "$repo" show audit-review:reports/2026-Q1-regulator-return.md | grep -c 'two inventory records')" = "1"

mkdir -p bundles
next_bundle="$fixture_tmp/retention-platform.bundle"
git -C "$repo" bundle create "$next_bundle" --all
git bundle verify "$next_bundle" >/dev/null
mv -f "$next_bundle" "$output_bundle"
echo "wrote $output_bundle at review $(git -C "$repo" rev-parse audit-review), production $(git -C "$repo" rev-parse production)"
