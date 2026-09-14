#!/usr/bin/env python3
"""No author-machine paths in shipped text.

A leftover `/Users/someone/...` is contamination at best and a broken COPY
source at worst — it says the file was authored against a local tree that no
container will ever have. The rubric reviewer flags this too; the grep catches
it before review.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

HOST_PATH = re.compile(
    r"/Users/[A-Za-z0-9._-]+|"
    r"/home/(?!agent\b|node\b|user\b|runner\b)[A-Za-z0-9._-]+|"
    r"[A-Z]:\\\\?(?:Users|Documents)|Documents and Settings")
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".woff", ".woff2",
                   ".ttf", ".otf", ".mp3", ".mp4", ".wasm", ".zip", ".db",
                   ".sqlite", ".sqlite3", ".ico", ".pdf"}


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
    err = make_err(errors)

    for path in sorted(task.rglob("*")):
        if not path.is_file() or path.suffix.lower() in BINARY_SUFFIXES:
            continue
        if "node_modules" in path.parts or path.name == "package-lock.json":
            continue
        # One finding per file. A saved log can carry hundreds of hits, and a
        # per-line report buries every other check's output under one problem.
        hits = []
        for i, line in enumerate(read_text(path).splitlines(), 1):
            m = HOST_PATH.search(line)
            if m:
                hits.append((i, m.group(0), line.strip()[:70]))
        if hits:
            i, found, snippet = hits[0]
            extra = (f" (and {len(hits) - 1} more line(s) in this file)"
                     if len(hits) > 1 else "")
            err(f"{path}:{i}: author-machine path {found!r} — {snippet!r}"
                f"{extra}. No container has this path.")

    return report("check-no-host-paths", task, errors, [])


if __name__ == "__main__":
    raise SystemExit(main())
