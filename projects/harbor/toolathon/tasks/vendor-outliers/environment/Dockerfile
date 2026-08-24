FROM us-central1-docker.pkg.dev/turing-delivery-rl-gym/daytona/task-image:1016beta

SHELL ["/bin/bash", "-c"]

RUN (command -v git >/dev/null 2>&1 || (apt-get update && apt-get install -y --no-install-recommends git)) \
    && rm -rf /var/lib/apt/lists/*

ARG RUNTIME_REPO=https://github.com/hkust-nlp/Toolathlon
ARG RUNTIME_REF=9be8d8fe07a497b18ee61e3f2ae694e9797f39eb
RUN git init -q /opt/runtime-src \
    && git -C /opt/runtime-src remote add origin ${RUNTIME_REPO} \
    && git -C /opt/runtime-src fetch -q --depth 1 origin ${RUNTIME_REF} \
    && git -C /opt/runtime-src checkout -q FETCH_HEAD \
    && rm -rf /opt/runtime-src/.git \
    && cp -a /opt/runtime-src/. /workspace/ \
    && rm -rf /opt/runtime-src \
    && rm -rf /workspace/tasks/finalpool

RUN apt-get update && apt-get install -y --no-install-recommends ripgrep \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

RUN cp -n configs/global_configs_example.py configs/global_configs.py \
    && cp -n configs/token_key_session_example.py configs/token_key_session.py

RUN uv sync --frozen 2>/dev/null || uv sync 2>/dev/null || true

RUN mkdir -p /workspace/dumps/workspace && chmod -R 0777 /workspace/dumps

COPY task/ /harbor_task/

RUN uv tool install 'harbor-rewardkit[documents]==0.1.*'

COPY runtime/ /workspace/runtime/
RUN chmod +x /workspace/runtime/*.sh
