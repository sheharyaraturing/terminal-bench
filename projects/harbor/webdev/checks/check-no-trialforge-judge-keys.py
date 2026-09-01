#!/usr/bin/env python3
"""No half-migrated grader files from a sibling suite.

A judge.toml carrying trialforge's text-answer keys (`files`, `target_claims`)
is graded as the wrong format — rewardkit hands the model file contents instead
of driving a browser, and the score means nothing. A leftover toolathon
`tests/<dim>/check.py` or `tests/expected/` is a Python grader this suite never
runs, so it looks like coverage that does not exist.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

FOREIGN_JUDGE_KEYS = {
    "files": "trialforge's text-answer judge reads file contents instead of "
             "driving a browser",
    "target_claims": "trialforge's claim-extraction contract",
    "atif_trajectory": "trialforge's trajectory grader",
}
FOREIGN_PATHS = {
    "tests/expected": "toolathon's expected-output fixtures — nothing here runs them",
}


def task_arg() -> Path:
    if len(sys.argv) < 2:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <task-dir>")
    task = Path(sys.argv[1])
    if not task.is_dir():
        sys.exit(f"FATAL: {task} is not a directory")
    return task


def load_toml(path: Path, err) -> dict:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


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
    err = make_err(errors)

    rubric_files = sorted((task / "tests").glob("*/judge.toml"))
    browser = task / "tests" / "rubric" / "browser" / "browser.toml"
    if browser.is_file():
        rubric_files.append(browser)

    for path in rubric_files:
        judge = load_toml(path, err).get("judge") or {}
        for key, why in FOREIGN_JUDGE_KEYS.items():
            if key in judge:
                err(f"{path}: [judge].{key} is a leftover from another suite ({why}). "
                    "A browser judge is driven by prompt_template plus an MCP "
                    "server; this key means the file was migrated halfway.")

    for stray in sorted((task / "tests").glob("*/check.py")):
        err(f"{stray}: a Python dimension grader from toolathon. Nothing in this "
            "project runs it, so it reads as coverage that does not exist.")

    for rel, why in FOREIGN_PATHS.items():
        if (task / rel).exists():
            err(f"{task / rel}: {why}.")

    return report("check-no-trialforge-judge-keys", task, errors, [])


if __name__ == "__main__":
    raise SystemExit(main())
