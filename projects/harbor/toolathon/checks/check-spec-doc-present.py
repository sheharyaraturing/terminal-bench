#!/usr/bin/env python3
"""The environment must carry a specification document the agent can discover.

Toolathon's design contract: the rules that decide the answer live in a
workspace document (policy doc, methodology sheet, SOP, taxonomy) that the
agent must find and read - not in the prompt. The prompt states the goal and
the output filename; the spec states the rules.

Human calibration of vendor-outliers (2026-08-19) found the failure mode this
guards: the workspace held only data files, so every rule had to live in the
instruction, and the task measured instruction-following instead of
spec-reading. Every task must ship at least one spec-bearing document
(.md / .docx / .pdf) under environment/task/initial_workspace/.
"""
from __future__ import annotations

import sys

from _lib import make_err, report, task_arg

SPEC_SUFFIXES = {".md", ".docx", ".pdf"}


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    workspace = task / "environment" / "task" / "initial_workspace"
    if not workspace.is_dir():
        err(f"{workspace}: missing. The agent's starting workspace must be committed "
            "here (check-required-files covers the broader layout).")
        return report("check-spec-doc-present", task, errors, notes)

    docs = sorted(
        p for p in workspace.rglob("*")
        if p.is_file() and p.suffix.lower() in SPEC_SUFFIXES
    )
    if not docs:
        err(f"{workspace}: no specification document ({', '.join(sorted(SPEC_SUFFIXES))}). "
            "The rules that decide the answer must be discoverable in the workspace - "
            "a policy doc, methodology sheet, SOP, or taxonomy - not stated only in the "
            "prompt. A prompt that carries the whole spec measures instruction-following, "
            "not spec-reading.")

    if docs:
        rel = [str(p.relative_to(workspace)) for p in docs]
        notes.append(f"{len(docs)} spec-bearing doc(s): {', '.join(rel[:4])}"
                     + (" ..." if len(rel) > 4 else ""))
    return report("check-spec-doc-present", task, errors, notes)


if __name__ == "__main__":
    sys.exit(main())
