#!/usr/bin/env python3
"""Top-level artifacts: the deliverables Harbor collects must be well-formed.

Toolathon declares deliverables in the top-level `artifacts` array (absolute
/app/... paths). 13/16 tasks set it; 3 omit it (doc-refiling, segment-growth,
vendor-outliers), so ABSENCE is a NOTE, not a FAIL.

When present, enforces:
  - a non-empty list of absolute paths under /app/
  - each artifact's basename appears in solution/solve.sh or a delegated sibling
    script (catches a stale artifacts list after a rename)
Also cross-references output filenames named in instruction.md against the list
(NOTE only - doa-routing does not name its file, so this can't be a hard FAIL).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from _lib import load_toml, make_err, read_text, report, task_arg

# Output filenames an instruction might name (xlsx/json/csv/md/txt/pptx).
OUT_FILE_RE = re.compile(r"\b([\w-]+\.(?:xlsx|json|csv|md|txt|pptx|docx))\b")


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    task_cfg = load_toml(task / "task.toml", err)
    artifacts = task_cfg.get("artifacts")

    if artifacts is None:
        notes.append("no top-level artifacts array - Harbor collects no deliverables. "
                     "3/16 tasks omit it; add it if the grader or a downstream step "
                     "needs the produced files as artifacts.")
        return report("check-artifacts", task, errors, notes)

    if not isinstance(artifacts, list) or not artifacts:
        err(f"{task}/task.toml: artifacts must be a non-empty array of absolute paths.")
        return report("check-artifacts", task, errors, notes)

    # The answer key for each declared artifact must exist under tests/expected/.
    expected_dir = task / "tests" / "expected"
    expected_names = {p.name for p in expected_dir.iterdir() if p.is_file()} if expected_dir.is_dir() else set()

    basenames: list[str] = []
    for i, a in enumerate(artifacts, 1):
        if isinstance(a, dict):  # ArtifactConfig table form: use the source path.
            a = a.get("source")
        if not isinstance(a, str) or not a.strip():
            err(f"{task}/task.toml: artifacts #{i} is not a non-empty path string.")
            continue
        if not a.startswith("/app/"):
            err(f"{task}/task.toml: artifacts entry {a!r} must be an absolute path under "
                "/app/ (the agent workdir contract).")
        base = Path(a).name
        basenames.append(base)
        if expected_dir.is_dir() and base not in expected_names:
            err(f"{task}/task.toml: artifact {a!r} has no answer key at "
                f"tests/expected/{base}. The dimension checks grade the produced file "
                "against the baked answer key; a name mismatch means a stale artifacts "
                "list after a rename.")

    # Cross-reference: files the instruction tells the agent to produce should be
    # collected as artifacts (NOTE only - some instructions are deliberately vague).
    instr = read_text(task / "instruction.md")
    named = {m.group(1) for m in OUT_FILE_RE.finditer(instr)}
    missing = sorted(n for n in named if n not in basenames)
    if named and missing:
        notes.append(f"instruction.md names output file(s) {missing} not in artifacts - "
                     "confirm they are collected or intentionally excluded.")

    return report("check-artifacts", task, errors, notes)


if __name__ == "__main__":
    sys.exit(main())
