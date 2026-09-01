#!/usr/bin/env python3
"""The task directory must be a slug-named DIRECT child of tasks/.

core/registry.py's list_tasks() enumerates `tasks/*` one level deep and takes
each directory name as the task id; resolve_task() then looks for
`tasks/<id>/`. A task nested one level deeper is invisible to the harness, and
the parent wrapper directory is surfaced as a task id with no task.toml behind
it. Separately, the repo-root common checks are bash and pass task paths
unquoted, so a directory name containing a space is split into two bogus paths
and every one of those checks reports a phantom failure.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.


def task_arg() -> Path:
    """The single positional argument: the task directory."""
    if len(sys.argv) < 2:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <task-dir>")
    task = Path(sys.argv[1])
    if not task.is_dir():
        sys.exit(f"FATAL: {task} is not a directory")
    return task


def make_err(errors: list[str]):
    def err(msg: str) -> None:
        errors.append(msg)

    return err


def report(name: str, task: Path, errors: list[str], notes: list[str]) -> int:
    """Print a uniform per-check report and return the process exit code."""
    for n in notes:
        print(f"NOTE {task}: {n}")
    if errors:
        for e in errors:
            print(f"FAIL {e}")
        print(f"{name}: {len(errors)} problem(s)")
        return 1
    print(f"{name}: OK ({task})")
    return 0

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MAX_SLUG_TOKENS = 3


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    resolved = task.resolve()
    parent = resolved.parent
    slug = resolved.name

    if parent.name != "tasks":
        err(f"{task}: task directory is not a direct child of tasks/ (its parent is "
            f"{parent.name!r}). core/registry.py enumerates tasks/* one level deep, "
            f"so this task is invisible to `harbor`/the autoreviewer and the wrapper "
            f"directory {parent.name!r} is instead listed as a task id with no "
            f"task.toml. Move it to tasks/{slug}/ and keep supporting material "
            "(spec docs, QC sheets, sample runs) outside tasks/.")

    if not SLUG_RE.match(slug):
        err(f"{task}: directory name {slug!r} is not a safe slug. Use lowercase "
            "letters, digits, and hyphens only — the repo-root common checks are "
            "bash and interpolate the task path unquoted, so a space or capital "
            "turns every one of them into a phantom failure.")

    # A working-copy suffix says a second, divergent copy of this task exists.
    WORKING_COPY = re.compile(
        r"(?:^|[-_])(?:copy|dup|duplicate|old|new|final|bak|backup|v\d+|"
        r"\d{4}-?\d{2}-?\d{2}|\(\d+\))$", re.IGNORECASE)
    if WORKING_COPY.search(slug):
        notes.append(f"{task}: directory name {slug!r} looks like a working-copy "
                     "suffix. Harbor publishes the directory name, so confirm a "
                     "second divergent copy is not sitting somewhere.")

    tokens = slug.count("-") + 1
    if SLUG_RE.match(slug) and tokens > MAX_SLUG_TOKENS:
        notes.append(f"slug has {tokens} hyphen-separated tokens (soft max "
                     f"{MAX_SLUG_TOKENS}); long slugs are unwieldy in CI logs and "
                     "artifact paths.")

    return report("check-task-layout", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
