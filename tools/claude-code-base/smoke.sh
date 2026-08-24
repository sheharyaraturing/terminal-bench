#!/usr/bin/env bash
set -euo pipefail
IMAGE="claude-code-base:0.1.0"
SHADOW="python:3.13-slim"
# 1. claude is on PATH and runs
docker run --rm "$IMAGE" claude --version
# 2. Harbor's install check would succeed (the exact command it runs)
docker run --rm "$IMAGE" bash -c 'export PATH="$HOME/.local/bin:$PATH"; command -v claude'
# 3. procps is present (claude-code's node-tree-kill needs it)
docker run --rm "$IMAGE" bash -c 'command -v ps && command -v pgrep'
# 4. The shadow tag must satisfy the harbor check wrapper: python AND claude
docker run --rm "$SHADOW" bash -c 'python --version && command -v claude'
echo "smoke: PASS"
