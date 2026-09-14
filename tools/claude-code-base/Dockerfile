FROM python:3.13-slim
# Pin the claude-code build baked into the image. Must be >= 2.1.x: harbor's
# claude-code agent emits `claude --effort <level>` when
# CLAUDE_CODE_EFFORT_LEVEL / reasoning_effort is set, and 2.0.0 rejects the
# flag with "unknown option '--effort'".
ARG CLAUDE_CODE_VERSION=2.1.260
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl procps ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://downloads.claude.ai/claude-code-releases/bootstrap.sh | bash -s -- ${CLAUDE_CODE_VERSION}
RUN ln -sf /root/.local/bin/claude /usr/local/bin/claude
