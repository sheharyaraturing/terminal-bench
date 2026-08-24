#!/usr/bin/env python3
"""Fixtures: git repos ship as bundles, never build-time clones or shallow clones.

CONTRIBUTING.md: a build-time clone makes the image non-reproducible and couples
the task to a live remote; --depth 1 throws away the history that git_git_log
exists to read.
"""
from __future__ import annotations

import re
import glob as globmod
from pathlib import Path

from _lib import make_err, read_text, report, task_arg

GIT_BUNDLE_MAGIC = (b"# v2 git bundle", b"# v3 git bundle")
SCAN_SUFFIXES = {".sh", ".py", ".sql"}


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    bundles = sorted(task.rglob("*.bundle"))
    for b in bundles:
        if b.parent != task / "environment" / "fixtures":
            err(f"{b}: bundles must live in {task}/environment/fixtures/ "
                "(that directory is the Docker build context)")
        head = b.open("rb").read(32)
        if not head.startswith(GIT_BUNDLE_MAGIC):
            err(f"{b}: not a git bundle (header is {head[:16]!r}). "
                "Create it with: git bundle create <name>.bundle --all")

    # Every .bundle referenced by a script must actually be committed. A missing
    # fixture is a container build failure 20 minutes into tier 2.
    referenced: set[str] = set()
    scan_files = [p for p in task.rglob("*")
                  if p.is_file() and (p.name == "Dockerfile" or p.suffix in SCAN_SUFFIXES)]
    for p in scan_files:
        text = read_text(p)
        if not text:
            continue
        for line in text.splitlines():
            # Comments only. tasks/TEMPLATE ships a worked example that names
            # fixtures/myrepo.bundle in a comment block; treating that as a
            # reference is a false positive on every task from the template.
            s = line.strip()
            if s.startswith("#") or s.startswith("--"):
                continue
            for m in re.finditer(r"[\w./-]+\.bundle", s):
                referenced.add(Path(m.group(0)).name)

    committed = {b.name for b in bundles}
    for name in sorted(referenced - committed):
        err(f"{task}: {name} is referenced but not committed under environment/fixtures/")
    for name in sorted(committed - referenced):
        notes.append(f"{name} is committed but never referenced by a Dockerfile/script")

    dockerfile = task / "environment" / "Dockerfile"
    if dockerfile.is_file():
        for i, line in enumerate(read_text(dockerfile).splitlines(), 1):
            s = line.strip()
            if s.startswith("#"):
                continue
            if re.search(r"git\s+clone\b", s) and re.search(r"https?://|git@|git://", s):
                err(f"{dockerfile}:{i}: build-time clone from a remote. "
                    "Commit a bundle under environment/fixtures/ and clone from that.")
            if re.search(r"--depth[ =]", s):
                err(f"{dockerfile}:{i}: --depth truncates history that git_git_log needs.")

        # Every COPY/ADD source must exist under environment/ (the build context).
        # A missing fixture is a container build failure 20 minutes into tier 2.
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
        # Split args, dropping flags like --from= / --chown= and any JSON-array form.
        rest = m.group(1)
        if rest.lstrip().startswith("["):
            # JSON array form: COPY ["src", "dest"] - rare here; skip rather than parse.
            continue
        tokens = [t for t in rest.split() if not t.startswith("--")]
        # Strip quotes around tokens.
        tokens = [t.strip('"').strip("'") for t in tokens]
        if len(tokens) < 2:
            continue
        sources, _dest = tokens[:-1], tokens[-1]
        for src in sources:
            # Skip URLs, absolute container paths, and build-arg references.
            if re.match(r"^[a-z]+://", src) or src.startswith("/") or "${" in src:
                continue
            if any(ch in src for ch in "*?["):
                # Glob source: pass if at least one match exists in the context.
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
