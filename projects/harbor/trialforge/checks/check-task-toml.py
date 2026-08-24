#!/usr/bin/env python3
"""task.toml: valid TOML, no docker_image (it skips the Dockerfile), secrets as ${VAR} templates."""
from __future__ import annotations

import re

from _lib import load_toml, make_err, report, task_arg

ENV_TEMPLATE = re.compile(r"\$\{[^}:]+(:-.*)?\}")


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    task_cfg = load_toml(task / "task.toml", err)
    image = (task_cfg.get("environment") or {}).get("docker_image")
    if image is not None:
        # Setting docker_image makes Harbor's should_use_prebuilt_docker_image()
        # return True, which pulls the image and SILENTLY SKIPS
        # environment/Dockerfile - so no fixtures are applied and claims about
        # them become unattainable. The base image is named in the Dockerfile's
        # FROM line instead (see tasks/TEMPLATE/task.toml).
        err(f"{task}/task.toml: [environment].docker_image is set to {image!r}. "
            "Harbor pulls a prebuilt image the moment this key exists and silently "
            "skips environment/Dockerfile, so fixtures never apply. Remove the key "
            "and name the base image in the Dockerfile FROM line.")
        if isinstance(image, str) and image.endswith(":latest"):
            notes.append("docker_image is also pinned to :latest - an immutable tag "
                         "would be required if the key were allowed at all.")

    # Secrets must arrive as ${VAR} templates that Harbor resolves from the
    # runner's process env. A literal value here is a credential committed to git.
    for section in ("verifier", "agent", "solution"):
        env = (task_cfg.get(section) or {}).get("env") or {}
        for k, v in env.items():
            if not (isinstance(v, str) and ENV_TEMPLATE.fullmatch(v)):
                err(f"{task}/task.toml: [{section}.env].{k} must be a ${{VAR}}"
                    " template, not a literal value. Harbor resolves templates from "
                    "the runner env at trial time.")

    # The rewardkit judge runs in the verifier container and routes through
    # OpenRouter via litellm, which reads OPENROUTER_API_KEY. Without this entry
    # the export in tests/test.sh resolves to empty, OpenRouter returns 401,
    # rewardkit raises, and `set -e` aborts before any reward file exists - which
    # Harbor reports as RewardFileNotFoundError, naming no cause.
    verifier_env = (task_cfg.get("verifier") or {}).get("env") or {}
    if "OPENROUTER_API_KEY" not in verifier_env:
        err(f"{task}/task.toml: [verifier.env].OPENROUTER_API_KEY is missing. The "
            "rewardkit judge needs it to reach OpenRouter; without it every trial "
            "fails with RewardFileNotFoundError. Add: "
            'OPENROUTER_API_KEY = "${OPENROUTER_API_KEY}".')

    return report("check-task-toml", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
