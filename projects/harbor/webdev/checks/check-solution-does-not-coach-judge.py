#!/usr/bin/env python3
"""The reference's served files must not contain scoring directives.

The judge observes the live page. Anything the reference renders — text, alt
attributes, HTML comments, inline scripts — is read by the same model that
assigns the score. A "score this 5/5" in the markup is a prompt injection that
the oracle itself plants, and it inflates the one run everybody trusts as the
ceiling. A criterion id in the page is the subtler version: it tells the judge
exactly which check it is looking at.

solve.sh comments are exempt: they explain the install and are never served.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

COACHING = re.compile(
    r"score this|assign (?:a )?(?:5|full|top)|full (?:marks|credit)|"
    r"ignore (?:your |the |all )?(?:previous |above )?instructions|"
    r"you are the judge|as the (?:judge|grader)|pass this criterion|"
    r"award (?:full|the) (?:score|credit)|this satisfies criterion",
    re.IGNORECASE)
SERVED_SUFFIXES = {".html", ".htm", ".css", ".js", ".mjs", ".jsx", ".ts", ".tsx",
                   ".svg", ".json"}


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


def criterion_ids(task: Path, err) -> set[str]:
    files = sorted((task / "tests").glob("*/judge.toml"))
    if not files:
        browser = task / "tests" / "rubric" / "browser" / "browser.toml"
        files = [browser] if browser.is_file() else []
    ids: set[str] = set()
    for f in files:
        for c in load_toml(f, err).get("criterion") or []:
            if isinstance(c, dict) and isinstance(c.get("id"), str):
                ids.add(c["id"])
    return ids


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    ids = criterion_ids(task, err)
    served = [p for p in sorted((task / "solution").rglob("*"))
              if p.is_file() and p.suffix.lower() in SERVED_SUFFIXES
              and "node_modules" not in p.parts and p.name != "package-lock.json"]

    for path in served:
        text = read_text(path)
        if not text:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            m = COACHING.search(line)
            if m:
                err(f"{path}:{i}: served file contains the scoring directive "
                    f"{m.group(0)!r}. The judge reads the rendered page — this is "
                    "an injection the reference itself plants.")
            for cid in sorted(ids):
                if re.search(rf"\b{re.escape(cid)}\b", line):
                    # A snake_case id can legitimately collide with a component
                    # name or a data-testid, so this is advisory.
                    notes.append(f"{path}:{i}: served file contains the string "
                                 f"{cid!r}, which is also a criterion id. Confirm "
                                 "it is coincidence and not the page telling the "
                                 "judge which check it is performing.")

    if not served:
        notes.append("the reference ships no browser-served files to scan.")
    return report("check-solution-does-not-coach-judge", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
