#!/usr/bin/env python3
"""[task].name must be context-mesh/<dirname> and match the task directory.

The name is the unique identifier across the repo (e.g. 'context-mesh/foo'); the
directory is 'tasks/foo'. A mismatch means a rename that didn't propagate - the
task is findable by directory but cross-references by name will dangle.
"""
from __future__ import annotations

import sys

from _lib import load_toml, make_err, report, task_arg

ORG = "context-mesh"


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    task_cfg = load_toml(task / "task.toml", err)
    name = (task_cfg.get("task") or {}).get("name")
    dirname = task.name

    if not isinstance(name, str) or not name.strip():
        err(f"{task}/task.toml: [task].name is required.")
        return report("check-task-name", task, errors, notes)

    if not name.startswith(f"{ORG}/"):
        err(f"{task}/task.toml: [task].name = {name!r} must be namespaced under "
            f"{ORG!r} (e.g. {ORG}/{dirname}).")

    suffix = name.rsplit("/", 1)[-1]
    if suffix != dirname:
        err(f"{task}/task.toml: [task].name = {name!r} but directory is "
            f"{dirname!r}. The last path component must match the directory "
            "name - a mismatch means a rename that didn't propagate.")

    return report("check-task-name", task, errors, notes)


if __name__ == "__main__":
    sys.exit(main())
