#!/usr/bin/env python3
"""NOTE-only: criteria that assert seeded facts should match the seed.

An LLM-graded assertion about seeded data has to be true of the data. If a
criterion says the board shows "Bay 4 — MAINTENANCE_HOLD" and the seed never
contains that phrase, either the seed drifted or the criterion is describing a
value the UI derives.

Advisory on purpose: a criterion legitimately talks about labels, formatted
totals, and statuses the app computes rather than stores, so a hard failure
here would flag correct rubrics constantly. The useful output is a short list
for the rubric reviewer to glance at.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

# Quoted, backticked, or ALL-CAPS-code-shaped literals inside a description.
LITERAL_RE = re.compile(r"`([^`\n]{3,40})`|\"([^\"\n]{3,40})\"")
# Sentinels are created by the judge, so they must NOT be in the seed —
# check-probe-not-in-seed.py owns that direction.
SENTINEL_RE = re.compile(r"^JUDGE[-_]|^Judge\s")
TEXT_SUFFIXES = {".json", ".csv", ".tsv", ".txt", ".sql", ".yaml", ".yml"}
MAX_REPORTED = 12


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


def load_toml(path: Path) -> dict:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def main() -> int:
    task = task_arg()
    assets = task / "environment" / "assets"
    seed_files = [p for p in sorted(assets.rglob("*"))
                  if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES] \
        if assets.is_dir() else []

    if not seed_files:
        print(f"NOTE {task}: no structured seed data; nothing to cross-check.")
        print(f"check-seed-literals-in-criteria: OK ({task})")
        return 0

    haystack = "\n".join(read_text(p) for p in seed_files)

    rubric_files = sorted((task / "tests").glob("*/judge.toml"))
    browser = task / "tests" / "rubric" / "browser" / "browser.toml"
    if browser.is_file():
        rubric_files.append(browser)

    missing: list[str] = []
    for path in rubric_files:
        for c in load_toml(path).get("criterion") or []:
            if not isinstance(c, dict):
                continue
            description = str(c.get("description", ""))
            for groups in LITERAL_RE.findall(description):
                literal = (groups[0] or groups[1]).strip()
                if not literal or SENTINEL_RE.match(literal):
                    continue
                # Prose in quotes is not a data literal.
                if " " in literal and not re.search(r"[A-Z0-9]{2,}|-\d", literal):
                    continue
                if literal not in haystack:
                    missing.append(f"{path.parent.name}/{c.get('id')}: {literal!r}")

    if missing:
        shown = missing[:MAX_REPORTED]
        print(f"NOTE {task}: {len(missing)} criterion literal(s) do not appear in "
              "the seed data. Each is either a value the UI derives (fine) or a "
              "seed that drifted from the rubric (not fine) — worth a glance:")
        for m in shown:
            print(f"NOTE {task}:   {m}")
        if len(missing) > len(shown):
            print(f"NOTE {task}:   … and {len(missing) - len(shown)} more")

    print(f"check-seed-literals-in-criteria: OK ({task})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
