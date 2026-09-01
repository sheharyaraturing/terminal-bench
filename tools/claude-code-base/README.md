# claude-code-base

Base Docker image with [Claude Code](https://claude.ai/code) pre-installed. Used by the autoreviewer pipeline to skip the ~3-5 minute `claude` installation that Harbor's claude-code agent performs on every run.

## How the skip works

Harbor's `ClaudeCode.install()` runs this check before installing:

```bash
export PATH="$HOME/.local/bin:$PATH"; command -v claude
```

If it succeeds, the install is skipped entirely. This image puts `claude` on PATH so both review legs skip the install.

## Where each leg gets its image

The two review legs do **not** use the task's `environment/Dockerfile`:

- **Rubric review (`harbor check`)** wraps the task in harbor's own `check-task-template`, which hardcodes `docker_image = "python:3.13-slim"` (a prebuilt image; no build ever happens). There is no CLI flag to override it.
- **Trajectory analysis (`harbor exec`)** takes `--image` explicitly, so we control it: `core/trajectory.py` builds `tools/trajectory-analysis/templates/Dockerfile`, which is `FROM claude-code-base:0.1.0`.

## The shadow tag (rubric leg)

Since the rubric wrapper's image name is hardcoded and Docker resolves unqualified names from the **local cache first** (never pulling when present), `build.sh` tags the built image twice:

```
claude-code-base:0.1.0   <- real name
python:3.13-slim         <- shadow of the wrapper's hardcoded image
```

The shadow is a strict superset of the real `python:3.13-slim` (same python, plus curl/procps/claude), so anything else on this machine expecting `python:3.13-slim` still works. It is local-only and affects nothing pushed anywhere.

To restore the real upstream image: `docker pull python:3.13-slim` (then re-run `build.sh` to re-apply the shadow; the build is fully cached so it takes seconds).

## Build locally

```bash
bash tools/claude-code-base/build.sh
```

Builds `claude-code-base:0.1.0` and applies the `python:3.13-slim` shadow tag.

## Smoke test

```bash
bash tools/claude-code-base/smoke.sh
```

Verifies `claude --version` runs, harbor's exact install-check command succeeds, `procps` is present, and the shadow tag has both `python` and `claude`.

## Push to a registry (when you have write access)

```bash
CLAUDE_CODE_BASE_REGISTRY=us-central1-docker.pkg.dev/turing-delivery-rl-gym/daytona \
  bash tools/claude-code-base/build.sh --push
```

Pushes only the real name (`claude-code-base:0.1.0`); the shadow tag is a local-machine mechanism and is never pushed. Other machines then need a one-time `docker pull <registry>/claude-code-base:0.1.0` plus a local re-tag as `python:3.13-slim` (re-running `build.sh` after the pull does this, since the build is cached).

## What's in the image

- `python:3.13-slim` base (debian; python 3.13, required by the check wrapper's verifier)
- `curl`, `procps`, `ca-certificates` (claude-code runtime deps)
- Claude Code 2.0.0 (via the official bootstrap installer)
- Symlink at `/usr/local/bin/claude` so it's on PATH for any user
