#!/usr/bin/env python3
"""instruction.md is a finished prompt, not a stub.

Placeholder scans catch unfinished *scaffolding*; this catches an unfinished
*prompt* — a few words that parse fine, ship fine, and give the agent nothing
to build.

Deliberately NOT checked here: lowercase openings, sentence fragments, missing
Oxford commas, informal grammar. A natural product request reads like a person
asking for something, and grepping for polish would fail exactly the prompts
that are doing it right. Voice is a rubric judgment.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

MIN_WORDS = int(os.environ.get("WEBDEV_INSTRUCTION_MIN_WORDS", "40"))
THIN_WORDS = int(os.environ.get("WEBDEV_INSTRUCTION_THIN_WORDS", "80"))
DRAFT_MARKER = re.compile(r"\b(TODO|FIXME|XXX|TBD|WIP)\b|<[a-z_]*placeholder[a-z_]*>|"
                          r"lorem ipsum", re.IGNORECASE)


def task_arg() -> Path:
    if len(sys.argv) < 2:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <task-dir>")
    task = Path(sys.argv[1])
    if not task.is_dir():
        sys.exit(f"FATAL: {task} is not a directory")
    return task


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


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

    path = task / "instruction.md"
    text = read_text(path)
    if not text.strip():
        err(f"{path}: missing or empty — the agent has nothing to build from.")
        return report("check-instruction-content", task, errors, notes)

    for i, line in enumerate(text.splitlines(), 1):
        for m in DRAFT_MARKER.finditer(line):
            err(f"{path}:{i}: draft marker {m.group(0)!r} in the prompt the agent "
                f"reads — {line.strip()[:90]!r}")

    words = len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", text))
    if words < MIN_WORDS:
        err(f"{path}: {words} words (minimum {MIN_WORDS}). A prompt this short "
            "cannot describe a product; the agent has to guess what to build and "
            "the judge grades it against criteria nobody stated.")
    elif words < THIN_WORDS:
        notes.append(f"instruction.md is {words} words. Many real product asks are "
                     "short, so this is not a failure — but confirm it names the "
                     "screens, the behaviours, and the runtime contract the "
                     "criteria will grade.")

    return report("check-instruction-content", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
