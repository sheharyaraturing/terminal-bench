#!/usr/bin/env python3
"""A batched dimension must tell the judge its criteria are independent.

In batched mode one session grades every criterion in the dimension. Without an
instruction to keep going after a failure and score each criterion on its own
evidence, a judge that fails criterion 2 routinely abandons 3 through 8 — the
dimension collapses to effectively binary and a submission that got most of it
right scores the same as one that got none of it.

Gate dimensions (`aggregation = "all_pass"`) are exempt: there, one failure
genuinely should sink the whole dimension.

The presence of the sentence is mechanical; whether it is well written is a
rubric judgment. Only an explicit statement of the opposite is a hard failure.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

INDEPENDENT = re.compile(
    r"continue to|continue after|independent|independently|on its own evidence|"
    r"each criterion|score each|do not stop|even if (?:an )?earlier|"
    r"separate check", re.IGNORECASE)
# The inverse: an instruction to abandon the dimension on first failure.
CONTAGIOUS = re.compile(
    r"if any criterion fails[^.]{0,60}(?:stop|skip|fail the (?:rest|remaining))|"
    r"stop (?:scoring|grading) (?:at|on) the first failure|"
    r"abandon the remaining criteria", re.IGNORECASE)


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

    targets: list[tuple[str, dict, str]] = []
    for path in sorted((task / "tests").glob("*/judge.toml")):
        cfg = load_toml(path, err)
        template = (cfg.get("judge") or {}).get("prompt_template")
        targets.append((str(path), cfg, template if isinstance(template, str) else ""))
    if not targets:
        rdir = task / "tests" / "rubric" / "browser"
        cfg = load_toml(rdir / "browser.toml", err)
        if cfg:
            name = (cfg.get("judge") or {}).get("prompt_template") or "prompt.md"
            targets.append((str(rdir / name), cfg, read_text(rdir / name)))

    for label, cfg, text in targets:
        if (cfg.get("judge") or {}).get("mode") != "batched":
            continue
        if (cfg.get("scoring") or {}).get("aggregation") == "all_pass":
            continue  # a gate dimension: one failure should sink it
        if not text:
            continue
        m = CONTAGIOUS.search(text)
        if m:
            err(f"{label}: instructs the judge to stop on the first failure "
                f"({m.group(0)!r}) in a batched, non-gate dimension. Every "
                "criterion after the first failure is scored 0 without being "
                "examined.")
        elif not INDEPENDENT.search(text):
            notes.append(f"{label}: batched and not an all_pass gate, but the prompt "
                         "never says to continue after a failure or to score each "
                         "criterion on its own evidence. A judge that gives up "
                         "midway collapses the dimension to binary.")

    return report("check-batched-independence-wording", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
