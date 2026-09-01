#!/usr/bin/env python3
"""Every TOML and JSON file the run depends on must parse.

An unescaped quote inside a multi-line prompt_template kills rewardkit before
any judge runs, and a malformed seed crashes the app on first boot. Both look
like infrastructure failures and neither names the file. Other checks parse
these too, but they stop at the first structural problem they care about; this
one exists to report the parser's own message, verbatim, for every file.
"""
from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.


def task_arg() -> Path:
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

    tomls = [p for p in sorted(task.rglob("*.toml")) if "node_modules" not in p.parts]
    for path in tomls:
        try:
            with path.open("rb") as fh:
                tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            err(f"{path}: invalid TOML - {exc}")
        except OSError as exc:
            err(f"{path}: unreadable - {exc}")

    jsons = [p for p in sorted(task.rglob("*.json"))
             if "node_modules" not in p.parts
             # Huge, machine-generated, and not load-bearing unless an image
             # installs from it — which check-solve-contract covers.
             and p.name != "package-lock.json"]
    for path in jsons:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            err(f"{path}: invalid JSON - {exc}")
        except (OSError, UnicodeDecodeError) as exc:
            err(f"{path}: unreadable - {exc}")

    notes.append(f"parsed {len(tomls)} TOML and {len(jsons)} JSON file(s).")
    return report("check-toml-and-json-parse", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
