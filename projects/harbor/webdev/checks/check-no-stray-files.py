#!/usr/bin/env python3
"""Nothing but the task itself may live in the task folder.

Everything under tasks/<slug>/ is part of the task: it is what gets published,
what gets uploaded into containers, and what a reviewer reads as the definition
of the work. Authoring by-products — spec documents, QC spreadsheets, sample
agent runs, zipped snapshots, editor droppings, build output — belong in the
PR or the QA record, not next to the thing being graded. Some of them are also
answer keys: a saved trial's trajectory.json contains a working solution.
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

# Extensions that are never part of a webdev task definition.
BAD_SUFFIXES = {
    ".zip": "a zipped snapshot of the task or of a trial",
    ".docx": "an authoring document",
    ".xlsx": "a QC spreadsheet",
    ".pptx": "an authoring document",
    ".pdf": "an authoring document (seed PDFs belong under environment/assets/)",
    ".db": "a built SQLite database — the app must seed its own on first boot",
    ".sqlite": "a built SQLite database",
    ".sqlite3": "a built SQLite database",
    ".log": "a captured run log",
    ".bak": "an editor backup",
    ".swp": "a vim swap file",
    ".orig": "a merge leftover",
    ".rej": "a rejected patch hunk",
}

BAD_NAMES = {
    ".DS_Store": "a macOS Finder dropping",
    "Thumbs.db": "a Windows Explorer dropping",
    "result.json": "a saved trial result",
    "trial.log": "a saved trial log",
    "job.log": "a saved job log",
    "lock.json": "a saved trial lock file",
    "trajectory.json": "a saved agent trajectory — it contains a working solution",
    "reward.json": "a saved trial reward",
    "reward.txt": "a saved trial reward",
}

# Directories that must never be committed inside a task.
BAD_DIRS = {
    "node_modules": "installed dependencies — solve.sh installs them from the lockfile",
    "dist": "frontend build output — the verifier builds it at grade time",
    "build": "build output",
    "__pycache__": "compiled Python",
    ".idea": "JetBrains project settings",
    ".vscode": "editor settings",
    ".venv": "a virtualenv",
    "logs": "captured run logs",
}

# A trial output directory: <task-slug>__<7 random chars>.
TRIAL_DIR_RE = re.compile(r"^.+__[A-Za-z0-9]{6,}$")

# The closed list at the task root. README.md and a rubrics/ copy of the
# implementation rubric are allowed alongside the format's own entries;
# anything else is authoring material or captured output that escaped.
ALLOWED_TOP_LEVEL = {"instruction.md", "task.toml", "environment", "solution",
                     "tests", "README.md", "rubrics"}


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    for path in sorted(task.rglob("*")):
        rel = path.relative_to(task)
        if path.is_dir():
            if path.name in BAD_DIRS:
                err(f"{path}: {BAD_DIRS[path.name]} must not be committed inside "
                    "the task.")
            elif TRIAL_DIR_RE.match(path.name):
                err(f"{path}: looks like a saved trial output directory. Sample "
                    "runs belong in the QA record, not in the task — a trajectory "
                    "in the task folder is an answer key.")
            continue
        if path.name in BAD_NAMES:
            err(f"{path}: {BAD_NAMES[path.name]} must not ship in the task folder.")
            continue
        if path.suffix.lower() in BAD_SUFFIXES:
            # environment/assets is the one place binary seed material belongs.
            if path.suffix.lower() == ".pdf" and str(rel).startswith("environment/assets"):
                continue
            err(f"{path}: {BAD_SUFFIXES[path.suffix.lower()]} must not ship in the "
                "task folder.")

    # Top-level shape is a closed list: everything under tasks/<slug>/ is
    # published, uploaded into containers, and read as the definition of the
    # task. A stray file here is at best noise and at worst a captured run that
    # names host paths or leaks the rubric.
    for child in sorted(task.iterdir()):
        if child.name.startswith("."):
            continue
        if child.name not in ALLOWED_TOP_LEVEL:
            kind = "directory" if child.is_dir() else "file"
            err(f"{child}: unexpected {kind} at the task root. The layout is "
                f"{sorted(ALLOWED_TOP_LEVEL)} — anything else is authoring "
                "material or captured output, and it ships with the task.")

    # Dead grading code: a file in tests/ that nothing runs is either an
    # abandoned experiment or a check somebody believes is running and is not.
    tests_dir = task / "tests"
    if tests_dir.is_dir():
        referenced = ""
        for f in (tests_dir / "test.sh", tests_dir / "test.py"):
            if f.is_file():
                referenced += f.read_text(encoding="utf-8", errors="replace")
        # Files the harness consumes directly rather than through test.sh:
        # Harbor builds tests/Dockerfile, and rewardkit reads tests/reward.toml
        # and each tests/<dimension>/judge.toml by discovery.
        harness_owned = {"test.sh", "test.py", "Dockerfile", "reward.toml",
                         ".dockerignore"}
        for f in sorted(tests_dir.iterdir()):
            if not f.is_file() or f.name in harness_owned:
                continue
            if f.name not in referenced:
                notes.append(f"{f} is never referenced by tests/test.sh or "
                             "tests/test.py. Dead grading code reads as a check that "
                             "runs when it does not — delete it or wire it in.")

    return report("check-no-stray-files", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
