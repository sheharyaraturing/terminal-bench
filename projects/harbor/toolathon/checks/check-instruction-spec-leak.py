#!/usr/bin/env python3
"""instruction.md should state the goal, not restate the specification.

Toolathon's contract: the prompt names the deliverable and points at the
workspace; the RULES live in the workspace spec docs (check-spec-doc-present).
Human calibration of segment-growth (2026-08-19) found the failure mode: the
prompt pre-disclosed every trap the Methodology sheet was built to test -
"with it, the task measures whether a model can follow four explicit rules;
without it, whether a model reads a methodology sheet before computing."

Two deterministic proxies, both NOTE-level (this is a heuristic; the semantic
judgment belongs to rubric review):

  1. Length. Thin prompts in this suite run ~35-105 words. Over the ceiling
     (default 120, tunable via INSTRUCTION_SPEC_MAX_WORDS) suggests embedded spec.
  2. Spec-language. Unambiguous rule-speak - rounding modes, statistical
     definitions, comparison operators spelled out - belongs in the spec doc,
     not the persona request.
"""
from __future__ import annotations

import os
import re
import sys

from _lib import read_text, report, task_arg

MAX_WORDS = int(os.environ.get("INSTRUCTION_SPEC_MAX_WORDS", "120"))

# Rule-speak that belongs in a methodology/policy doc, not in the persona's ask.
SPEC_PATTERNS = [
    (r"\bROUND_(HALF_UP|HALF_EVEN|UP|DOWN)\b", "rounding mode"),
    (r"\bstandard deviations?\b", "statistical threshold definition"),
    (r"\bstrictly greater than\b", "comparison operator"),
    (r"\bpopulation vs\.? sample\b", "estimator distinction"),
    (r"\bdecimal arithmetic\b", "arithmetic implementation directive"),
    (r"\bmean plus\b", "threshold formula"),
]


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []

    instr = task / "instruction.md"
    text = read_text(instr)
    if not text.strip():
        return report("check-instruction-spec-leak", task, errors,
                      ["no instruction.md; see check-required-files"])

    words = len(text.split())
    if words > MAX_WORDS:
        notes.append(f"{instr}: {words} words (thin prompts in this suite run ~35-105). "
                     "A long prompt usually restates rules that belong in the workspace "
                     "spec docs - calibration of segment-growth found the prompt "
                     "pre-disclosing every trap the Methodology sheet was built to test.")

    for pattern, label in SPEC_PATTERNS:
        m = re.search(pattern, text, re.I)
        if m:
            line = text[:m.start()].count("\n") + 1
            notes.append(f"{instr}:{line}: {label} ({m.group()!r}) in the prompt. "
                         "Rule-speak like this belongs in the workspace spec doc; the "
                         "prompt should name the deliverable and let the agent find the "
                         "rules.")

    return report("check-instruction-spec-leak", task, errors, notes)


if __name__ == "__main__":
    sys.exit(main())
