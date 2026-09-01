#!/usr/bin/env python3
"""[task].name must be <org>/<dirname>, with the org drawn from a known set.

The name is the published package id. A last component that has drifted from
the directory means a rename that did not propagate: the task is still findable
by directory, but every cross-reference by name dangles.

Two orgs are in use. The current format publishes under "codearena" (see
tasks/bazaarbridge-marketplace); the earlier browser-rubric tasks publish under
"webdev". Both are accepted; mixing a shape with the other shape's org is a
NOTE, since it is usually an unfinished migration rather than a decision.
"""
from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

ORGS = {o.strip() for o in
        os.environ.get("WEBDEV_ORGS", "codearena,webdev").split(",") if o.strip()}
# The org each task shape publishes under by convention.
SHAPE_ORG = {"dimensions": "codearena", "browser-rubric": "webdev"}


def task_arg() -> Path:
    """The single positional argument: the task directory."""
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
                       tests/test.py. The earlier format; fleetops and
                       torquebay-enterprise still use it.
    """
    if sorted((task / "tests").glob("*/judge.toml")):
        return "dimensions"
    if (task / "tests" / "rubric" / "browser" / "browser.toml").is_file():
        return "browser-rubric"
    return "unknown"


def load_toml(path: Path, err) -> dict:
    """Parse TOML with the same parser Harbor/RewardKit use. Errors go to err."""
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


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    toml_path = task / "task.toml"
    cfg = load_toml(toml_path, err)
    name = (cfg.get("task") or {}).get("name")
    dirname = task.resolve().name

    if not isinstance(name, str) or not name.strip():
        err(f"{toml_path}: [task].name is required "
            f"(expected <org>/{dirname}, org one of {sorted(ORGS)}).")
        return report("check-task-name", task, errors, notes)

    org, _, suffix = name.rpartition("/")
    if not org:
        err(f"{toml_path}: [task].name = {name!r} is not namespaced. Use "
            f"<org>/{dirname} with org one of {sorted(ORGS)}.")
    elif org not in ORGS:
        err(f"{toml_path}: [task].name = {name!r} uses org {org!r}, which is not "
            f"one of {sorted(ORGS)}. Harbor publishes under the package name, so "
            "a stray org makes the published id inconsistent with the suite.")

    if suffix != dirname:
        err(f"{toml_path}: [task].name = {name!r} but the directory is {dirname!r}. "
            "The last path component must match the directory name — a mismatch "
            "means a rename that did not propagate.")

    shape = task_shape(task)
    expected = SHAPE_ORG.get(shape)
    if expected and org in ORGS and org != expected:
        notes.append(f"this is a {shape!r}-shaped task published under {org!r}; that "
                     f"shape conventionally publishes under {expected!r}. Fine if "
                     "deliberate, but it usually means a half-finished migration.")

    return report("check-task-name", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
