#!/usr/bin/env python3
"""The task layout exists, for whichever verifier shape the task uses.

Every later check reads one of these files; a missing one turns into a
confusing cascade of unrelated failures rather than "you forgot the rubric".
"""
from __future__ import annotations

import sys
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

# Required of every task, whatever its verifier shape.
COMMON_FILES = ["instruction.md", "task.toml", "environment/Dockerfile",
                "solution/solve.sh"]
# environment/assets is deliberately NOT required: a static page, a
# client-only game, or a generative-art task may legitimately ship no seed.
# It becomes required only when instruction.md points the agent at it.
COMMON_DIRS: list[str] = []

# The current format: rewardkit discovers tests/<dimension>/judge.toml, and the
# verifier runs in its own image built from tests/Dockerfile.
DIMENSION_FILES = ["tests/reward.toml", "tests/test.sh", "tests/Dockerfile"]

# The earlier format: one browser rubric driven by a Python verifier that starts
# the app in the shared agent container.
BROWSER_FILES = ["tests/test.sh", "tests/test.py",
                 "tests/rubric/browser/browser.toml",
                 "tests/rubric/browser/prompt.md",
                 "solution/app/APP_MANIFEST.md"]

# Review scaffolding or an answer key that nobody remembers is there.
FORBIDDEN = ["NOTES.md", "SOLUTION.md", "ANSWERS.md", ".env"]


def task_arg() -> Path:
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


def make_err(errors: list[str]):
    def err(msg: str) -> None:
        errors.append(msg)

    return err


def report(name: str, task: Path, errors: list[str], notes: list[str]) -> int:
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

    shape = task_shape(task)
    if shape == "unknown":
        err(f"{task}: no recognisable verifier. Expected either "
            "tests/<dimension>/judge.toml files alongside tests/reward.toml (the "
            "current format), or tests/rubric/browser/browser.toml driven by "
            "tests/test.py (the earlier one). Without one of those the task has "
            "no rubric and cannot be scored.")
        return report("check-required-files", task, errors, notes)

    required = list(COMMON_FILES)
    required += DIMENSION_FILES if shape == "dimensions" else BROWSER_FILES

    for rel in required:
        if not (task / rel).is_file():
            err(f"{task / rel}: missing (required by the {shape} task layout)")
    for rel in COMMON_DIRS:
        if not (task / rel).is_dir():
            err(f"{task / rel}: missing (required by the task layout)")

    # A solve.sh with nothing beside it copies nothing: there is no reference
    # app, so the oracle can never establish that the task is solvable.
    solution = task / "solution"
    if solution.is_dir():
        payload = [p for p in solution.rglob("*")
                   if p.is_file() and p.name != "solve.sh"
                   and "node_modules" not in p.parts]
        if not payload:
            err(f"{solution}: holds only solve.sh. There is no reference app, so "
                "the oracle installs nothing and the task has never been shown to "
                "be solvable.")

    # The assets mount is required only if the prompt sends the agent there.
    assets = task / "environment" / "assets"
    instruction = ""
    try:
        instruction = (task / "instruction.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        pass
    if "/assets/" in instruction and not assets.is_dir():
        err(f"{assets}: instruction.md points the agent at /assets/ but the "
            "directory does not exist, so the image mounts nothing and the agent "
            "is told to read files that are not there.")

    for rel in FORBIDDEN:
        if (task / rel).exists():
            notes.append(f"{task / rel}: review scaffolding should not ship inside "
                         "the task folder — it becomes an answer key nobody "
                         "remembers is there.")

    if shape == "dimensions":
        dims = sorted(p.parent.name for p in (task / "tests").glob("*/judge.toml"))
        if len(dims) < 2:
            notes.append(f"only {len(dims)} graded dimension ({dims}). The format "
                         "scores a weighted mean across dimensions; one collapses "
                         "the reward to a single judge's opinion.")
        # A dimension directory holding anything but its judge.toml is usually a
        # stray prompt draft that no longer matches the one being used.
        for d in dims:
            extra = [p.name for p in (task / "tests" / d).iterdir()
                     if p.name != "judge.toml" and not p.name.startswith(".")]
            if extra:
                notes.append(f"tests/{d}/ holds {extra} beside judge.toml; only "
                             "judge.toml is read.")
    else:
        notes.append("this task uses the earlier browser-rubric shape "
                     "(tests/rubric/browser/ + tests/test.py). The current format "
                     "is tests/reward.toml + tests/<dimension>/judge.toml with a "
                     "separate verifier image — see tasks/bazaarbridge-marketplace.")
        if not (task / "tests/rubric/browser/segments.json").is_file():
            notes.append("no segments.json - the browser rubric will run as ONE "
                         "judge session.")

    return report("check-required-files", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
