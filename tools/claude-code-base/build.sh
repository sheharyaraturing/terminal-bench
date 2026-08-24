#!/usr/bin/env bash
set -euo pipefail
REGISTRY="${CLAUDE_CODE_BASE_REGISTRY:-}"
IMAGE_NAME="claude-code-base:0.1.0"
FULL_NAME="${REGISTRY:+$REGISTRY/}$IMAGE_NAME"
# harbor check/analyze hardcode python:3.13-slim as their wrapper image.
# Shadowing that tag locally makes those wrappers pick up claude for free:
# docker resolves unqualified names from the local cache and never pulls.
SHADOW_TAG="python:3.13-slim"
docker build -t "$IMAGE_NAME" "$(dirname "$0")"
docker tag "$IMAGE_NAME" "$SHADOW_TAG"
echo "shadowed $SHADOW_TAG -> $IMAGE_NAME (local only; restore with: docker pull $SHADOW_TAG)"
if [ -n "$REGISTRY" ]; then docker tag "$IMAGE_NAME" "$FULL_NAME"; fi
if [ "${1:-}" = "--push" ]; then
    [ -z "$REGISTRY" ] && { echo "ERROR: --push requires CLAUDE_CODE_BASE_REGISTRY" >&2; exit 1; }
    docker push "$FULL_NAME"
    echo "pushed: $FULL_NAME"
else
    echo "built locally: $IMAGE_NAME"
fi
