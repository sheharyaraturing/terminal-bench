#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$ROOT}"
PINNED="751f8c148222e58aa173c83c4e5e6cfccb2cc124"
UPSTREAM_URL="https://github.com/theskumar/python-dotenv.git"

mkdir -p "$OUT/bundles"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [[ -n "${UPSTREAM_REPO:-}" ]]; then
  git clone --no-local "$UPSTREAM_REPO" "$WORK/upstream"
elif [[ -s "$ROOT/bundles/python-dotenv-upstream.bundle" ]]; then
  git clone "$ROOT/bundles/python-dotenv-upstream.bundle" "$WORK/upstream"
else
  git clone --filter=blob:none --no-checkout "$UPSTREAM_URL" "$WORK/upstream"
fi

git -C "$WORK/upstream" cat-file -e "$PINNED^{commit}"
git -C "$WORK/upstream" checkout --detach "$PINNED"
test "$(git -C "$WORK/upstream" rev-parse HEAD)" = "$PINNED"
test -s "$WORK/upstream/LICENSE"
git -C "$WORK/upstream" branch -f main "$PINNED"
git -C "$WORK/upstream" config pack.threads 1
git -C "$WORK/upstream" bundle create "$OUT/bundles/python-dotenv-upstream.bundle" refs/heads/main
git -C "$WORK/upstream" bundle verify "$OUT/bundles/python-dotenv-upstream.bundle"

git clone "$OUT/bundles/python-dotenv-upstream.bundle" "$WORK/internal"
git -C "$WORK/internal" checkout -B main "$PINNED"
git -C "$WORK/internal" branch --unset-upstream || true
git -C "$WORK/internal" remote remove origin
git -C "$WORK/internal" config user.name "Fixture Release Bot"
git -C "$WORK/internal" config user.email "fixture-release@example.invalid"
git -C "$WORK/internal" config commit.gpgSign false
git -C "$WORK/internal" config core.autocrlf false
git -C "$WORK/internal" config pack.threads 1

commit_at() {
  local timestamp="$1"
  local message="$2"
  GIT_AUTHOR_NAME="Fixture Release Bot" \
  GIT_AUTHOR_EMAIL="fixture-release@example.invalid" \
  GIT_COMMITTER_NAME="Fixture Release Bot" \
  GIT_COMMITTER_EMAIL="fixture-release@example.invalid" \
  GIT_AUTHOR_DATE="$timestamp" \
  GIT_COMMITTER_DATE="$timestamp" \
    git -C "$WORK/internal" commit --no-gpg-sign -m "$message"
}

mkdir -p "$WORK/internal/docs" "$WORK/internal/deploy"
cp "$ROOT/repo_overlay/INTERNAL_FORK_NOTICE.md" "$WORK/internal/INTERNAL_FORK_NOTICE.md"
cp "$ROOT/repo_overlay/docs/replacement-contract.md" "$WORK/internal/docs/replacement-contract.md"
cp "$ROOT/repo_overlay/docs/evidence-authority.md" "$WORK/internal/docs/evidence-authority.md"
cp "$ROOT/repo_overlay/v0.8.0/replacement.py" "$WORK/internal/src/dotenv/replacement.py"
git -C "$WORK/internal" add INTERNAL_FORK_NOTICE.md docs src/dotenv/replacement.py
commit_at "2026-06-01T10:00:00Z" "internal: add direct dotenv replacement command"
git -C "$WORK/internal" tag replace-v0.8.0

cp "$ROOT/repo_overlay/v0.8.1/replacement.py" "$WORK/internal/src/dotenv/replacement.py"
git -C "$WORK/internal" add src/dotenv/replacement.py
commit_at "2026-06-15T11:00:00Z" "internal: unlink checked targets before replacement"
git -C "$WORK/internal" tag replace-v0.8.1

cp "$ROOT/repo_overlay/v0.9.0/replacement.py" "$WORK/internal/src/dotenv/replacement.py"
git -C "$WORK/internal" add src/dotenv/replacement.py
commit_at "2026-07-01T12:00:00Z" "internal: replace targets through a temporary file"
git -C "$WORK/internal" tag replace-v0.9.0

cp "$ROOT/repo_overlay/v0.9.1/replacement.py" "$WORK/internal/src/dotenv/replacement.py"
git -C "$WORK/internal" add src/dotenv/replacement.py
commit_at "2026-07-20T13:00:00Z" "internal: simplify replacement with os.replace"
git -C "$WORK/internal" tag replace-v0.9.1

cp "$ROOT/repo_overlay/v1.0.0-rc1/replacement.py" "$WORK/internal/src/dotenv/replacement.py"
git -C "$WORK/internal" add src/dotenv/replacement.py
commit_at "2026-08-10T14:00:00Z" "internal: adopt the upstream rewrite transaction"
git -C "$WORK/internal" tag replace-v1.0.0-rc1

cp "$ROOT/repo_overlay/deploy/image-manifest.toml" "$WORK/internal/deploy/image-manifest.toml"
git -C "$WORK/internal" add deploy/image-manifest.toml
commit_at "2026-08-17T17:30:00Z" "deploy: record incident-cutoff image manifest"
git -C "$WORK/internal" tag prod-2026-08-17

git -C "$WORK/internal" fsck --full
git -C "$WORK/internal" bundle create "$OUT/bundles/dotenv-replacement-internal.bundle" \
  refs/heads/main \
  refs/tags/replace-v0.8.0 \
  refs/tags/replace-v0.8.1 \
  refs/tags/replace-v0.9.0 \
  refs/tags/replace-v0.9.1 \
  refs/tags/replace-v1.0.0-rc1 \
  refs/tags/prod-2026-08-17
git -C "$WORK/internal" bundle verify "$OUT/bundles/dotenv-replacement-internal.bundle"

git -C "$WORK/internal" show-ref --head | LC_ALL=C sort > "$OUT/bundles/internal-history.refs"
printf '%s\n' "$PINNED" > "$OUT/bundles/upstream-pinned-sha.txt"
