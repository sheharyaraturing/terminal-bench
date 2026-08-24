#!/usr/bin/env python3
"""task.toml: valid TOML, the toolathon field contract, secrets as ${VAR} templates.

Toolathon tasks are Harbor schema 1.4 with a gateway tool surface. This check
enforces the invariant fields every toolathon task carries, and rejects the
trialforge-only fields that signal a task was written against the wrong format.
"""
from __future__ import annotations

import re
import sys

from _lib import env_block, load_toml, make_err, report, task_arg

ENV_TEMPLATE = re.compile(r"\$\{[^}:]+(:-.*)?\}")

# Fields that belong to the trialforge (MCP-Atlas) format, not toolathon. Their
# presence means the task was written against the wrong spec.
TRIALFORGE_ONLY = ["enabled_tools", "persona", "domain", "target_tool_calls", "target_claims"]


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    task_cfg = load_toml(task / "task.toml", err)
    if not task_cfg:
        return report("check-task-toml", task, errors, notes)

    # schema_version
    if task_cfg.get("schema_version") != "1.4":
        err(f"{task}/task.toml: schema_version = {task_cfg.get('schema_version')!r}, "
            "expected \"1.4\".")

    # No docker_image: it makes Harbor pull a prebuilt image and silently skip
    # environment/Dockerfile, so fixtures never apply.
    image = (task_cfg.get("environment") or {}).get("docker_image")
    if image is not None:
        err(f"{task}/task.toml: [environment].docker_image is set to {image!r}. Harbor "
            "pulls a prebuilt image the moment this key exists and silently skips "
            "environment/Dockerfile. Remove the key and name the base image in the "
            "Dockerfile FROM line.")

    # [task].keywords must include "tool-use".
    keywords = (task_cfg.get("task") or {}).get("keywords")
    if not (isinstance(keywords, list) and "tool-use" in keywords):
        err(f"{task}/task.toml: [task].keywords must include \"tool-use\", got {keywords!r}.")

    # The gateway tool surface: [environment.env] must carry the three keys.
    env = env_block(task_cfg, "environment")
    for key in ("MCP_SERVERS", "LOCAL_TOOLS", "GATEWAY_PORT"):
        if not isinstance(env.get(key), str) or not env.get(key):
            err(f"{task}/task.toml: [environment.env].{key} is required and must be a "
                "non-empty string (it wires the gateway tool surface).")

    # [verifier.env].TASK_ID present (the rewardkit run is keyed on it).
    verifier_env = env_block(task_cfg, "verifier")
    if not isinstance(verifier_env.get("TASK_ID"), str) or not verifier_env.get("TASK_ID"):
        err(f"{task}/task.toml: [verifier.env].TASK_ID is required.")

    # Secrets must be ${VAR} templates, never literals committed to git.
    for section in ("verifier", "agent", "solution"):
        sec_env = env_block(task_cfg, section)
        for k, v in sec_env.items():
            # TASK_ID / MCP_SERVERS / etc. are plain config, not secrets; only
            # flag values that look like credentials (key/token/secret in name).
            if not re.search(r"(?i)(key|token|secret|password)", k):
                continue
            if not (isinstance(v, str) and ENV_TEMPLATE.fullmatch(v)):
                err(f"{task}/task.toml: [{section}.env].{k} must be a ${{VAR}} template, "
                    "not a literal value. Harbor resolves templates from the runner env.")

    # Reject trialforge-only metadata fields.
    meta = task_cfg.get("metadata") or {}
    for field in TRIALFORGE_ONLY:
        if field in meta:
            err(f"{task}/task.toml: [metadata].{field} is a trialforge (MCP-Atlas) field, "
                "not toolathon. Toolathon selects tools via [environment.env].MCP_SERVERS "
                "and carries only difficulty + category in [metadata].")

    return report("check-task-toml", task, errors, notes)


if __name__ == "__main__":
    sys.exit(main())
