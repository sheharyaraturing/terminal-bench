FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl procps ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://downloads.claude.ai/claude-code-releases/bootstrap.sh | bash -s -- 2.0.0
RUN ln -sf /root/.local/bin/claude /usr/local/bin/claude
