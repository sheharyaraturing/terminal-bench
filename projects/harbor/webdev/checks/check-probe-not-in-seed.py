#!/usr/bin/env python3
"""Grader probe values must not already exist in the seed or the reference.

Criteria that verify a create/update flow name a distinctive sentinel — a
`JUDGE-SKU-9001`, a `Judge Lantern` — and then confirm exactly one such record
exists. If that value is already in the seed data or hard-coded in the
reference's markup, a read-only app that creates nothing still "finds" it, and
the create criterion passes on evidence the submission never produced.

Skipped entirely when the rubric names no sentinels, which is the normal case
for a static page, a game, or a generative-art task.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

# `JUDGE-SKU-9001`, `JUDGE_PERSIST_1`, and the `Judge Lantern` naming pattern.
PROBE_RE = re.compile(r"\bJUDGE[-_][A-Z0-9][A-Z0-9-]*\b|\bJudge\s+[A-Z][a-z]+\b")


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
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        err(f"{path}: not valid TOML - {e}")
    return {}


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


def rubric_files(task: Path) -> list[Path]:
    files = sorted((task / "tests").glob("*/judge.toml"))
    if files:
        return files
    browser = task / "tests" / "rubric" / "browser" / "browser.toml"
    return [browser] if browser.is_file() else []


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    probes: set[str] = set()
    for path in rubric_files(task):
        cfg = load_toml(path, err)
        for c in cfg.get("criterion") or []:
            if isinstance(c, dict):
                probes |= set(PROBE_RE.findall(str(c.get("description", ""))))

    if not probes:
        print(f"NOTE {task}: the rubric names no grader sentinels "
              "(JUDGE-… / 'Judge <Name>'); nothing to collide with.")
        print(f"check-probe-not-in-seed: OK ({task})")
        return 0

    # Where a pre-existing copy would let a read-only app pass a create check.
    haystacks = [p for p in (task / "environment").rglob("*") if p.is_file()]
    haystacks += [p for p in (task / "solution").rglob("*")
                  if p.is_file() and p.suffix in
                  (".html", ".htm", ".js", ".mjs", ".jsx", ".json", ".css", ".sql")]

    for path in sorted(haystacks):
        text = read_text(path)
        if not text:
            continue  # binary or unreadable: a sentinel there cannot be rendered
        for probe in sorted(probes):
            if probe in text:
                err(f"{path}: contains the grader probe {probe!r}. A criterion "
                    "creates that record and then confirms exactly one exists — "
                    "with it pre-seeded, an app that creates nothing still passes.")

    return report("check-probe-not-in-seed", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
