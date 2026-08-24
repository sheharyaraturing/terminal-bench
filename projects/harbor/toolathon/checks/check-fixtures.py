#!/usr/bin/env python3
"""Fixtures: COPY sources must exist; no unpinned build-time remote clones.

Toolathon fixtures are CSV/XLSX/MD/SQL files copied into the image (not git
bundles). This check enforces:
  - every relative COPY/ADD source in environment/Dockerfile resolves under
    environment/ (the build context) - a missing source is a build failure
  - no build-time `git clone` from a live remote EXCEPT the pinned Toolathlon
    runtime (RUNTIME_REPO + RUNTIME_REF, where REF is an immutable 40-hex SHA)
"""
from __future__ import annotations

import glob as globmod
import re
from pathlib import Path

from _lib import make_err, read_text, report, task_arg

# The one allowed build-time clone: the pinned Toolathlon runtime. REF must be a
# full commit SHA, not a branch tip, so the image is reproducible.
RUNTIME_REPO_RE = re.compile(r"RUNTIME_REPO\s*=\s*https://github\.com/hkust-nlp/Toolathlon")
SHA_RE = re.compile(r"RUNTIME_REF\s*=\s*[0-9a-f]{40}\b")


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    dockerfile = task / "environment" / "Dockerfile"
    if not dockerfile.is_file():
        return report("check-fixtures", task, errors,
                      ["no environment/Dockerfile; see check-required-files"])

    lines = read_text(dockerfile).splitlines()

    # No build-time remote clones other than the pinned runtime.
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith("#"):
            continue
        if re.search(r"git\s+clone\b", s) and re.search(r"https?://|git@|git://", s):
            # Allowed only if it clones the pinned runtime repo via the ARGs.
            if "${RUNTIME_REPO}" in s or "$RUNTIME_REPO" in s:
                continue
            err(f"{dockerfile}:{i}: build-time clone from a remote. Only the pinned "
                "Toolathlon runtime (RUNTIME_REPO/RUNTIME_REF) may be cloned at build "
                "time; commit other fixtures under environment/ and COPY them.")

    # If a runtime clone is present, its REF must be a full SHA.
    body = "\n".join(lines)
    if RUNTIME_REPO_RE.search(body) and not SHA_RE.search(body):
        err(f"{dockerfile}: RUNTIME_REF must be a full 40-character commit SHA, not a "
            "branch or tag - otherwise the image is not reproducible.")

    _check_copy_sources(task, dockerfile, err)

    return report("check-fixtures", task, errors, notes)


def _check_copy_sources(task: Path, dockerfile: Path, err) -> None:
    """Verify each relative COPY/ADD source resolves to a real path under environment/."""
    context = task / "environment"
    for i, line in enumerate(read_text(dockerfile).splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^(?:COPY|ADD)\s+(.*)$", s)
        if not m:
            continue
        rest = m.group(1)
        if rest.lstrip().startswith("["):
            continue  # JSON array form; rare here.
        tokens = [t for t in rest.split() if not t.startswith("--")]
        tokens = [t.strip('"').strip("'") for t in tokens]
        if len(tokens) < 2:
            continue
        sources, _dest = tokens[:-1], tokens[-1]
        for src in sources:
            if re.match(r"^[a-z]+://", src) or src.startswith("/") or "${" in src:
                continue
            if any(ch in src for ch in "*?["):
                if not globmod.glob(str(context / src)):
                    err(f"{dockerfile}:{i}: COPY source glob {src!r} matches nothing "
                        f"under {context}. The build will fail when the image is built.")
                continue
            if not (context / src).exists():
                err(f"{dockerfile}:{i}: COPY source {src!r} does not exist under "
                    f"{context}. Commit the fixture or fix the path - the image build "
                    "fails on a missing source.")


if __name__ == "__main__":
    raise SystemExit(main())
