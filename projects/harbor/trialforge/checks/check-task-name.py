#!/usr/bin/env python3
"""[task].name must match the task directory name.

The name is the unique identifier across the repo (e.g. 'turing/foo'); the
directory is 'tasks/foo'. A mismatch means a rename that didn't propagate —
the task is findable by directory but cross-references by name will dangle.
"""
from __future__ import annotations

import sys

from _lib import load_toml, make_err, report, task_arg


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    err = make_err(errors)

    task_cfg = load_toml(task / "task.toml", err)
    name = (task_cfg.get("task") or {}).get("name")
    dirname = task.name

    if not isinstance(name, str) or not name.strip():
        err(f"{task}/task.toml: [task].name is required.")
        return report("check-task-name", task, errors, [])

    suffix = name.rsplit("/", 1)[-1]
    if suffix != dirname:
        err(f"{task}/task.toml: [task].name = {name!r} but directory is "
            f"{dirname!r}. The last path component must match the directory "
            "name — a mismatch means a rename that didn't propagate.")

    return report("check-task-name", task, errors, [])


if __name__ == "__main__":
    sys.exit(main())
