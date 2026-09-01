#!/usr/bin/env python3
"""task.toml: the Harbor contract, per verifier shape.

The mechanical shape only — whether the difficulty rating is honest is the
rubric reviewer's job. What is checked here is every field whose absence or
wrong placement fails silently at trial time rather than loudly at authoring
time.

The two shapes declare genuinely different things, and conflating them would
either wave through a broken current-format task or fail the earlier ones for
not carrying fields their runtime never reads.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

SCHEMA_VERSION = "1.4"

# Present in every task, whatever the shape.
REQUIRED_TASK = ("name", "version", "description")
REQUIRED_METADATA = ("category", "difficulty")

# The current format: a codex judge reaching OpenRouter from a separate
# verifier container that is allowed to talk to exactly one host.
DIMENSION_VERIFIER_ENV = {"OPENROUTER_API_KEY": "${OPENROUTER_API_KEY}"}
# The earlier format: claude-code driven through the Anthropic-compatible
# gateway, in the shared agent container.
BROWSER_VERIFIER_ENV = {
    "OPENROUTER_API_KEY": "${OPENROUTER_API_KEY}",
    "ANTHROPIC_BASE_URL": "https://openrouter.ai/api",
    "ANTHROPIC_AUTH_TOKEN": "${OPENROUTER_API_KEY}",
    "ANTHROPIC_API_KEY": "",
    "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY": "1",
}


def task_arg() -> Path:
    if len(sys.argv) < 2:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <task-dir>")
    task = Path(sys.argv[1])
    if not task.is_dir():
        sys.exit(f"FATAL: {task} is not a directory")
    return task


def task_shape(task: Path) -> str:
    """Which verifier convention this task follows.

    "dimensions"     - tests/reward.toml plus one tests/<dimension>/judge.toml
                       per graded dimension. The current format; see
                       tasks/bazaarbridge-marketplace.
    "browser-rubric" - a single tests/rubric/browser/browser.toml driven by
                       tests/test.py. The earlier format.
    """
    if sorted((task / "tests").glob("*/judge.toml")):
        return "dimensions"
    if (task / "tests" / "rubric" / "browser" / "browser.toml").is_file():
        return "browser-rubric"
    return "unknown"


def load_toml(path: Path, err) -> dict:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        err(f"{path}: missing")
    except tomllib.TOMLDecodeError as e:
        err(f"{path}: not valid TOML - {e}")
    return {}


def make_err(errors: list[str]):
    def err(msg: str) -> None:
        errors.append(msg)

    return err


def report(name: str, task: Path, errors: list[str], notes: list[str]) -> int:
    for n in notes:
        print(f"NOTE {task}: {n}")
    if errors:
        for e in errors:
            print(f"FAIL {e}")
        print(f"{name}: {len(errors)} problem(s)")
        return 1
    print(f"{name}: OK ({task})")
    return 0


def check_common(path: Path, cfg: dict, err, notes: list[str]) -> None:
    if cfg.get("schema_version") != SCHEMA_VERSION:
        err(f"{path}: schema_version = {cfg.get('schema_version')!r}, expected "
            f"{SCHEMA_VERSION!r}.")

    tsk = cfg.get("task")
    if not isinstance(tsk, dict):
        err(f"{path}: missing [task] block.")
        tsk = {}
    for field in REQUIRED_TASK:
        if not str(tsk.get(field, "")).strip():
            err(f"{path}: [task].{field} is required and must be non-empty.")
    keywords = tsk.get("keywords")
    if not isinstance(keywords, list) or not keywords:
        err(f"{path}: [task].keywords must be a non-empty list.")
    elif "webdev" not in [str(k).lower() for k in keywords]:
        notes.append("[task].keywords does not include \"webdev\". A forgotten "
                     "keyword breaks no run, but it is how these tasks are found.")

    # Fields borrowed from a sibling suite: they parse, they are never read,
    # and they make the task look like it configures something it does not.
    FOREIGN = {"enabled_tools": "trialforge", "persona": "trialforge",
               "target_claims": "trialforge", "MCP_SERVERS": "toolathon",
               "LOCAL_TOOLS": "toolathon", "GATEWAY_PORT": "toolathon"}
    for block_name, block in (("task", tsk), ("metadata", cfg.get("metadata") or {}),
                              ("environment", cfg.get("environment") or {}),
                              ("environment.env",
                               (cfg.get("environment") or {}).get("env") or {})):
        if not isinstance(block, dict):
            continue
        for key, suite in FOREIGN.items():
            if key in block:
                err(f"{path}: [{block_name}].{key} is a {suite} field. Nothing in "
                    "this project reads it, so it documents configuration that "
                    "does not exist.")

    meta = cfg.get("metadata")
    if not isinstance(meta, dict):
        err(f"{path}: missing [metadata] block.")
        meta = {}
    for field in REQUIRED_METADATA:
        if not str(meta.get(field, "")).strip():
            err(f"{path}: [metadata].{field} is required and must be non-empty.")
    if meta.get("difficulty") not in (None, "easy", "medium", "hard"):
        err(f"{path}: [metadata].difficulty = {meta.get('difficulty')!r}, expected "
            "one of easy/medium/hard.")

    for section in ("agent", "verifier"):
        block = cfg.get(section)
        if not isinstance(block, dict):
            err(f"{path}: missing [{section}] block.")
            continue
        t = block.get("timeout_sec")
        if not isinstance(t, (int, float)) or isinstance(t, bool) or t <= 0:
            err(f"{path}: [{section}].timeout_sec must be a positive number, got "
                f"{t!r}.")

    # Harbor reads artifacts from the top level. Nested under [verifier] it
    # parses fine and is then silently dropped.
    if "artifacts" in (cfg.get("verifier") or {}):
        err(f"{path}: artifacts is nested under [verifier]. Harbor reads it from "
            "the TOP LEVEL and silently drops it here — move it out.")

    env = cfg.get("environment")
    if not isinstance(env, dict):
        err(f"{path}: missing [environment] block.")
        env = {}
    for field in ("cpus", "memory_mb"):
        if env.get(field) is None:
            err(f"{path}: [environment].{field} is required.")
    # Resourcing is a sizing judgment, not a contract. A static page needs far
    # less than a full-stack app, and failing a task over it would block work
    # that runs perfectly well.
    mem = env.get("memory_mb")
    if isinstance(mem, (int, float)) and mem < 4096:
        notes.append(f"[environment].memory_mb = {mem}. Chromium, the app, and the "
                     "judge share this container; below ~4096 MB a heavy app risks "
                     "an OOM that looks like a bad submission.")
    cpus = env.get("cpus")
    if isinstance(cpus, (int, float)) and cpus < 2:
        notes.append(f"[environment].cpus = {cpus}; a browser judge is happier "
                     "with at least 2.")
    # A prebuilt image makes Harbor skip environment/Dockerfile entirely, so
    # the pre-installed dependencies and `COPY assets/` never happen — and the
    # agent meets an empty container the task assumed was provisioned.
    if env.get("docker_image"):
        err(f"{path}: [environment].docker_image = {env['docker_image']!r} makes "
            "Harbor skip environment/Dockerfile. The baked dependencies and the "
            "COPY of assets/ never happen, and the agent gets a container the "
            "task never provisioned.")
    mem_cap = env.get("memory_mb")
    if isinstance(mem_cap, (int, float)) and mem_cap > 16384:
        err(f"{path}: [environment].memory_mb = {mem_cap} is above the 16384 "
            "ceiling; a request that large will not schedule.")

    if "allow_internet" in env:
        err(f"{path}: [environment].allow_internet is set alongside network_mode. "
            "Use network_mode only — the pair is redundant and can disagree.")

    venv = (cfg.get("verifier") or {}).get("env")
    if not isinstance(venv, dict) or not venv:
        err(f"{path}: missing [verifier.env]. The judge reads its credentials and "
            "model selection from it.")
        return
    for key in ("REWARDKIT_JUDGE", "REWARDKIT_MODEL"):
        if not str(venv.get(key, "")).strip():
            err(f"{path}: [verifier.env].{key} is required.")

    # A literal secret is both a committed credential and a run that only works
    # on the author's machine. check-no-literal-secrets.py sweeps the tree; this
    # is the same rule at the one place it matters most.
    for key, value in venv.items():
        looks_secret = any(w in key.lower()
                           for w in ("key", "token", "secret", "password"))
        if looks_secret and isinstance(value, str) and value.strip() \
                and not value.startswith("${"):
            err(f"{path}: [verifier.env].{key} holds a literal value rather than a "
                "${VAR} template.")


def check_dimensions(path: Path, cfg: dict, err, notes: list[str]) -> None:
    verifier = cfg.get("verifier") or {}
    venv = verifier.get("env") or {}

    for key, expected in DIMENSION_VERIFIER_ENV.items():
        if venv.get(key) != expected:
            err(f"{path}: [verifier.env].{key} = {venv.get(key)!r}, expected "
                f"{expected!r}.")

    # The verifier runs in its own image and only sees what it declares.
    if verifier.get("environment_mode") != "separate":
        err(f"{path}: [verifier].environment_mode = "
            f"{verifier.get('environment_mode')!r}, expected \"separate\". Shared "
            "mode runs the verifier inside the agent's container, where it "
            "inherits agent-installed packages and any file the agent wrote — "
            "including the grading code itself.")

    vhost = verifier.get("environment")
    if not isinstance(vhost, dict):
        err(f"{path}: missing [verifier.environment]. Separate mode needs the "
            "verifier image and its network policy declared.")
        vhost = {}
    if not str(vhost.get("docker_image", "")).strip():
        err(f"{path}: [verifier.environment].docker_image is required — it is the "
            "image tests/Dockerfile builds into.")
    # The judge must reach OpenRouter and nothing else. An open verifier can be
    # steered outward by a submission that plants instructions in its own UI.
    if vhost.get("network_mode") != "allowlist":
        notes.append(f"[verifier.environment].network_mode = "
                     f"{vhost.get('network_mode')!r}, not \"allowlist\". The judge "
                     "reads pages the submission wrote, so an unrestricted verifier "
                     "gives a prompt injection somewhere to send them.")
    hosts = vhost.get("allowed_hosts")
    if not isinstance(hosts, list) or not hosts:
        err(f"{path}: [verifier.environment].allowed_hosts must list the hosts the "
            "judge needs (at minimum the model gateway).")
    # Which host the allowlist must contain depends on which provider key is
    # wired; check-allowlist-matches-provider.py resolves that properly.

    # The agent phase is offline in this format, so the image must already carry
    # the app's runtime dependencies. check-dockerfiles.py verifies it does.
    if (cfg.get("environment") or {}).get("network_mode") is None:
        notes.append("[environment].network_mode is unset, so the agent phase "
                     "inherits Harbor's default rather than the format's "
                     "\"no-network\". State it explicitly.")


def check_browser_rubric(path: Path, cfg: dict, err, notes: list[str]) -> None:
    venv = (cfg.get("verifier") or {}).get("env") or {}
    for key, expected in BROWSER_VERIFIER_ENV.items():
        if key not in venv:
            err(f"{path}: [verifier.env].{key} is missing (expected {expected!r}).")
        elif venv[key] != expected:
            err(f"{path}: [verifier.env].{key} = {venv[key]!r}, expected {expected!r}.")

    artifacts = cfg.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        err(f"{path}: top-level artifacts = [...] is required for this shape. The "
            "verifier grades the app in place, so without it the delivered /app is "
            "destroyed with the container and no failed trial can be diagnosed.")
    elif "/app" not in [a for a in artifacts if isinstance(a, str)]:
        err(f"{path}: artifacts does not include \"/app\" — the app root is what "
            "the verifier starts and the judge grades.")

    # Shared mode: both phases run in the one container, which needs the network
    # for npm and for the judge's model calls.
    for section in ("agent", "verifier"):
        block = cfg.get(section) or {}
        if block.get("network_mode") != "public":
            notes.append(f"[{section}].network_mode = "
                         f"{block.get('network_mode')!r}. This shape installs npm "
                         "packages at trial time and calls OpenRouter from the "
                         "judge; confirm both still work without public network.")

    # Documentation fields: their absence never breaks a run, so they are
    # reported for the reviewer rather than blocking the task.
    meta = cfg.get("metadata") or {}
    for field in ("difficulty_explanation", "task_id"):
        if not str(meta.get(field, "")).strip():
            notes.append(f"[metadata].{field} is unset; the other tasks of this "
                         "shape carry it.")
    authors = (cfg.get("task") or {}).get("authors")
    if not isinstance(authors, list) or not authors:
        notes.append("[task].authors is unset; the other tasks of this shape "
                     "carry { name, email } entries.")


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    path = task / "task.toml"
    cfg = load_toml(path, err)
    if not cfg:
        return report("check-task-toml", task, errors, notes)

    shape = task_shape(task)
    check_common(path, cfg, err, notes)
    if shape == "dimensions":
        check_dimensions(path, cfg, err, notes)
    elif shape == "browser-rubric":
        check_browser_rubric(path, cfg, err, notes)
    else:
        notes.append("verifier shape not recognised; only the shape-independent "
                     "fields were checked (see check-required-files).")

    return report("check-task-toml", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
