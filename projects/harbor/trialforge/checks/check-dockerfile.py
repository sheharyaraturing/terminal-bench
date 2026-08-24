#!/usr/bin/env python3
"""environment/Dockerfile contract: cleared entrypoint, pinned base image.

Harbor supplies its own agent process; the image's ENTRYPOINT runs envsubst +
the sandbox CMD and would fight it. The wrapper starts both services itself.
Without ENTRYPOINT [] nothing works, and the symptom is a health-check timeout
that looks like a network fault.
"""
from __future__ import annotations

import re

from _lib import IMAGE_PREFIX, load_toml, make_err, read_text, report, task_arg


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    err = make_err(errors)

    dockerfile = task / "environment" / "Dockerfile"
    if not dockerfile.is_file():
        # A task with no environment/ overrides runs the base image as-is;
        # required-files does not demand a Dockerfile, so this is not an error.
        return report("check-dockerfile", task, errors,
                      ["no environment/Dockerfile; task runs the base image directly"])

    dtext = read_text(dockerfile)
    dlines = [l for l in dtext.splitlines() if l.strip() and not l.strip().startswith("#")]
    body = "\n".join(dlines)

    if not re.search(r"^\s*ENTRYPOINT\s*\[\s*\]\s*$", body, re.M):
        err(f"{dockerfile}: must contain `ENTRYPOINT []`. Harbor runs its own "
            "agent process; the image entrypoint must be cleared or the wrapper "
            "never gets to start the sandbox and the harness.")

    froms = re.findall(r"^\s*FROM\s+(\S+)", body, re.M)
    for f in froms:
        if not f.startswith(IMAGE_PREFIX):
            err(f"{dockerfile}: FROM {f} - must build on {IMAGE_PREFIX}<tag>")

    # task.toml docker_image tag must match the Dockerfile FROM tag, or one is stale.
    task_cfg = load_toml(task / "task.toml", err)
    image = (task_cfg.get("environment") or {}).get("docker_image")
    if isinstance(image, str) and image.startswith(IMAGE_PREFIX):
        base_tags = {f.split(":")[-1] for f in froms if f.startswith(IMAGE_PREFIX)}
        if base_tags and image.split(":")[-1] not in base_tags:
            err(f"{task}: task.toml docker_image tag {image.split(':')[-1]!r} does not match "
                f"the Dockerfile FROM tag(s) {sorted(base_tags)}. One of the two is stale.")

    return report("check-dockerfile", task, errors, [])


if __name__ == "__main__":
    raise SystemExit(main())
