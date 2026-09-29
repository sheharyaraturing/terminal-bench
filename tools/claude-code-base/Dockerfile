FROM python:3.13-slim
# Pin the claude-code build baked into the image. harbor's claude-code agent
# skips its own install whenever `claude` is already on PATH, so this pin is
# the version every review runs. Floor: 2.1.280 (claude-opus-5-5 is rejected
# by older builds); 2.1.x also provides the `--effort` flag harbor passes.
ARG CLAUDE_CODE_VERSION=2.1.283
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl procps ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://downloads.claude.ai/claude-code-releases/bootstrap.sh | bash -s -- ${CLAUDE_CODE_VERSION}
RUN ln -sf /root/.local/bin/claude /usr/local/bin/claude
