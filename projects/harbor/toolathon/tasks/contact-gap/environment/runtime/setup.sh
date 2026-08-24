set -euo pipefail

export PATH="/root/.local/bin:${PATH}"
cd /workspace

mkdir -p /logs/artifacts
exec > >(tee -a /logs/artifacts/setup.log) 2>&1

TASK="${TASK_ID:?TASK_ID must be set, e.g. harbor/doa-routing}"
PORT="${GATEWAY_PORT:-8765}"
BUNDLE=/workspace/dumps/task_bundle.json
GATEWAY_LOG=/logs/artifacts/gateway.log
TASK_PATH="/workspace/tasks/${TASK}"

health() { curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; }

if health; then
    echo "Gateway already healthy on port ${PORT}"
    exit 0
fi

if [ ! -d "$TASK_PATH" ]; then
    mkdir -p "$TASK_PATH"
    cp -a /harbor_task/. "$TASK_PATH/"
fi

json_array() {
    printf '%s' "$1" | tr ',' '\n' | sed 's/^ *//; s/ *$//' | grep -v '^$' \
        | sed 's/.*/"&"/' | paste -sd, - | sed 's/^/[/; s/$/]/'
}

if [ ! -f "$TASK_PATH/task_config.json" ]; then
    cat > "$TASK_PATH/task_config.json" <<EOF
{
  "needed_mcp_servers": $(json_array "$MCP_SERVERS"),
  "needed_local_tools": $(json_array "${LOCAL_TOOLS:-claim_done}"),
  "meta": {}
}
EOF
fi

if [ ! -f "$TASK_PATH/docs/task.md" ]; then
    mkdir -p "$TASK_PATH/docs"
    echo "Harbor supplies this task's instruction at run time; see instruction.md." \
        > "$TASK_PATH/docs/task.md"
fi

if [ ! -f "$BUNDLE" ]; then
    uv run python -m scripts.decoupled.container_preprocess \
        --eval_config "${EVAL_CONFIG_PATH:-scripts/formal_run_v0.json}" \
        --task_dir "$TASK" \
        --max_steps_under_single_turn_mode "${MAX_STEPS:-100}" \
        --model_short_name "${MODEL_SHORT_NAME:-harbor-agent}" \
        --provider unified --bundle_file "$BUNDLE" --debug
fi

chmod -R 0777 /workspace/dumps

WORKSPACE="$(uv run python -c 'import json,sys; print(json.load(open(sys.argv[1]))["container_paths"]["agent_workspace"])' "$BUNDLE")"
ln -sfn "$WORKSPACE" /app
echo "Linked /app -> ${WORKSPACE}"

if ! pgrep -f container_tool_gateway >/dev/null 2>&1; then
    ln -sf "$GATEWAY_LOG" /workspace/dumps/gateway.log
    nohup uv run python -m scripts.decoupled.container_tool_gateway \
        --bundle_file "$BUNDLE" --host 0.0.0.0 --port "$PORT" --debug \
        > "$GATEWAY_LOG" 2>&1 &
fi

for _ in $(seq 1 30); do
    if health; then
        echo "Gateway healthy on port ${PORT}"
        exit 0
    fi
    sleep 2
done

tail -n 20 "$GATEWAY_LOG"
exit 1
