#!/usr/bin/env python3
"""instruction.md: content beyond the grep-level hygiene checks.

check-instruction-hygiene catches tool/server/grader leaks and CHANGE-ME
placeholders. This check catches the other unfinished-prompt signals:

  - TODO/FIXME markers (a prompt still being drafted)
  - A too-short instruction (a stub that slipped past the placeholder check)

The minimum word count is tunable via INSTRUCTION_MIN_WORDS (default 50).
The bootstrap task's instruction is ~130 words; a real persona request is
at least a paragraph.
"""
from __future__ import annotations

import os
import re
import sys

from _lib import make_err, read_text, report, task_arg

TODO_RE = re.compile(r"\b(TODO|FIXME)\b")
MIN_WORDS = int(os.environ.get("INSTRUCTION_MIN_WORDS", "50"))


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    err = make_err(errors)

    instr = task / "instruction.md"
    text = read_text(instr)
    if not text.strip():
        err(f"{instr}: empty or missing. check-required-files also enforces this, "
            "but this check cannot proceed without content.")
        return report("check-instruction-content", task, errors, [])

    for m in TODO_RE.finditer(text):
        line = text[:m.start()].count("\n") + 1
        err(f"{instr}:{line}: unfinished marker {m.group()!r}. The instruction "
            "must read as a finished persona request, not a draft.")

    word_count = len(text.split())
    if word_count < MIN_WORDS:
        err(f"{instr}: {word_count} words, expected at least {MIN_WORDS}. A real "
            "persona request is at least a paragraph; a stub slipped past the "
            "placeholder checks.")

    return report("check-instruction-content", task, errors, [])


if __name__ == "__main__":
    sys.exit(main())
