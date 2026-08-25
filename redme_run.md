# Running Trialforge Tasks (parallel) from the CLI

These commands do the same thing as the **Run review** button in the web UI —
they call `POST /api/execute` on the local server. The server must already be
running (see below).

## Prerequisites

1. Python venv + deps installed:
   ```bash
   python3.11 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

2. Start the API/UI server (needs network for the Anthropic + OpenRouter calls):
   ```bash
   .venv/bin/python execute.py --serve
   ```
   It listens on http://127.0.0.1:8000.

3. Required env vars in `.env`:
   - `ANTHROPIC_API_KEY` — used by the rubric leg (claude-code / Opus 5).
   - `OPENROUTER_API_KEY` — used by the validation verifier. Without it the
     validation leg skips with "harbor run failed to produce a reward".

4. Harbor CLI + Docker installed (for the rubric `harbor check` and validation
   `harbor run` legs):
   ```bash
   uv tool install --python python3.13 'harbor[modal]'
   ```
   `harbor` requires Python >= 3.12.

## Run all trialforge tasks in parallel

Fires every task under `projects/harbor/trialforge/tasks/` at once. Each
`POST /api/execute` returns immediately with a `run_id`; the server runs them
in background threads.

```bash
cd /Users/utkarshsoni/Documents/Turing/TerminalBenchAutochecks/terminal-bench

for t in projects/harbor/trialforge/tasks/*/; do
  task=$(basename "$t")
  curl -s -X POST http://127.0.0.1:8000/api/execute \
    -H "Content-Type: application/json" \
    -d "{\"project_name\":\"trialforge\",\"data\":{\"task_id\":\"$task\"}}" \
    -o "/tmp/run_$task.json" &
done
wait

echo "--- submitted runs ---"
cat /tmp/run_*.json
```

## Run all tasks in parallel with a concurrency cap

Every rubric leg builds its own Docker container and launches a claude-code
agent, so 12 in parallel is heavy on CPU/RAM/Docker. Use `xargs -P4` to cap
concurrency (4 at a time):

```bash
cd /Users/utkarshsoni/Documents/Turing/TerminalBenchAutochecks/terminal-bench

ls -d projects/harbor/trialforge/tasks/*/ | xargs -n1 basename \
  | xargs -I{} -P4 curl -s -X POST http://127.0.0.1:8000/api/execute \
    -H "Content-Type: application/json" \
    -d '{"project_name":"trialforge","data":{"task_id":"{}"}}'
```

## Run a single task

```bash
curl -s -X POST http://127.0.0.1:8000/api/execute \
  -H "Content-Type: application/json" \
  -d '{"project_name":"trialforge","data":{"task_id":"flag-precedence-conflict"}}' \
  | python3 -m json.tool
```

## Poll a run's status / logs

```bash
# Status JSON
curl -s http://127.0.0.1:8000/api/runs/<run_id> | python3 -m json.tool

# Live log
tail -f runs/<run_id>/log.txt
```

## Notes / gotchas

- **API quota:** if the Anthropic key hits its workspace spend limit, the
  rubric leg skips with `You have reached your specified workspace API usage
  limits`. Swap in a key with quota or wait for the reset date in the message.
- **Agent setup timeout:** installing claude-code inside the slim container
  (apt + download) can exceed Harbor's default 360s. `core/rubric.py` and
  `core/validation.py` raise it via `agent_setup_timeout_multiplier`
  (override with the `HARBOR_AGENT_SETUP_TIMEOUT_MULTIPLIER` env var, default
  `3.0`).
- **Rubric model:** defaults to `claude-opus-5` (override with the
  `HARBOR_CHECK_MODEL` env var).
- **Rubric outer timeout:** 50 min (`HARBOR_CHECK_TIMEOUT_SEC` in
  `core/rubric.py`).
- **Environment backend:** defaults to local Docker. Set
  `HARBOR_ENV_BACKEND` to run the rubric (`harbor check`) and validation
  (`harbor run` oracle/nop) legs in a remote backend instead. Accepted
  values: `docker`, `modal`, `daytona`, `e2b`, `runloop`, `gke`,
  `apple-container`. Unset = Docker (current behaviour, unchanged).

## Running on Daytona

Daytona is a Harbor environment backend — the rubric and validation legs
run inside a Daytona sandbox instead of local Docker. The local CLI
reads `HARBOR_ENV_BACKEND` and passes `--env <backend>` to both
`harbor check` and `harbor run`.

1. Install Harbor **with the daytona extra** (the backend SDK ships as
   an optional extra; the plain/modal install won't recognise daytona):
   ```bash
   uv tool install --python 3.12 "harbor[daytona]==0.14.0"
   ```

2. Put your Daytona credentials in `.env` (exact var names per your
   Harbor/Daytona version — check `harbor env --help`). The local Docker
   build step is skipped for non-docker backends; Harbor builds the image
   inside Daytona instead.

3. Run with the backend selected:
   ```bash
   HARBOR_ENV_BACKEND=daytona .venv/bin/python execute.py \
     --project trialforge --taskid flag-precedence-conflict
   ```
   The progress log prints `[env: daytona]` on the rubric and oracle/nop
   lines so you can confirm the backend is active.

4. Parallel runs inherit the same backend — just export it before the
   `curl` loop:
   ```bash
   export HARBOR_ENV_BACKEND=daytona
   for t in projects/harbor/trialforge/tasks/*/; do ...; done
   ```

To drop back to local Docker, unset the var (`unset HARBOR_ENV_BACKEND`)
or set `HARBOR_ENV_BACKEND=docker`.
