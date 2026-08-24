#!/usr/bin/env python3
"""environment/Dockerfile: the toolathon image contract.

All 16 toolathon Dockerfiles are byte-identical; this check enforces the
load-bearing invariants without pinning the exact tag (so a tag bump is a
one-line change, not a check edit):
  - FROM the task-image base (not :latest)
  - the pinned Toolathlon runtime clone (RUNTIME_REPO + RUNTIME_REF, REF a 40-hex SHA)
  - `uv sync` (runtime deps install)
  - harbor-rewardkit[documents] installed
  - COPY task/ and COPY runtime/ into the image

Unlike trialforge there is NO ENTRYPOINT [] requirement - the toolathon image
uses SHELL/WORKDIR/uv, not a cleared entrypoint.
"""
from __future__ import annotations

import re
import sys

from _lib import IMAGE_PREFIX, make_err, read_text, report, task_arg

SHA_RE = re.compile(r"RUNTIME_REF\s*=\s*[0-9a-f]{40}\b")


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    dockerfile = task / "environment" / "Dockerfile"
    if not dockerfile.is_file():
        return report("check-dockerfile-toolathon", task, errors,
                      ["no environment/Dockerfile; see check-required-files"])

    body = "\n".join(
        l for l in read_text(dockerfile).splitlines()
        if l.strip() and not l.strip().startswith("#")
    )

    # FROM the task-image base, pinned to an immutable tag.
    froms = re.findall(r"^\s*FROM\s+(\S+)", body, re.M)
    if not froms:
        err(f"{dockerfile}: no FROM line.")
    for f in froms:
        if not f.startswith(IMAGE_PREFIX):
            err(f"{dockerfile}: FROM {f} - must build on {IMAGE_PREFIX}<tag>")
        elif f.endswith(":latest"):
            err(f"{dockerfile}: FROM {f} - pin an immutable tag, not :latest.")

    # The pinned Toolathlon runtime clone.
    if "RUNTIME_REPO" not in body:
        err(f"{dockerfile}: no RUNTIME_REPO ARG - the Toolathlon runtime clone is missing.")
    if not SHA_RE.search(body):
        err(f"{dockerfile}: RUNTIME_REF must be a full 40-character commit SHA (immutable), "
            "not a branch or tag - otherwise the image is not reproducible.")

    # Runtime deps + rewardkit.
    if not re.search(r"\buv\s+sync\b", body):
        err(f"{dockerfile}: no `uv sync` - the Toolathlon runtime dependencies are not "
            "installed.")
    if "harbor-rewardkit" not in body:
        err(f"{dockerfile}: harbor-rewardkit is not installed - tests/test.sh invokes it "
            "via uvx and the grade would fail with a missing tool.")

    # The task + runtime must be copied into the image. Source tokens end in a
    # slash (e.g. `COPY task/ /harbor_task/`), so match the token followed by
    # whitespace rather than a word boundary (which fails after a trailing `/`).
    for src in ("task/", "runtime/"):
        if not re.search(rf"^\s*(?:COPY|ADD)\s+{re.escape(src)}(?=\s|$)", body, re.M):
            err(f"{dockerfile}: no COPY of {src} into the image. The runtime setup and "
                "task fixtures live there.")

    return report("check-dockerfile-toolathon", task, errors, notes)


if __name__ == "__main__":
    sys.exit(main())
