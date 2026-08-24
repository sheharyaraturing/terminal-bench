#!/usr/bin/env python3
"""solution/solve.sh must emit an answer the grader can actually see.

Harbor's OracleAgent captures solve.sh's stdout into /logs/agent/oracle.txt, and
the rewardkit grader reads the produced artifacts. A solve.sh that computes
quietly, or writes to a path nobody reads, scores the oracle ~0 however correct
it is.

This check is intentionally shallow - it does not run the script. It requires:
  1. non-trivial content beyond the shebang / `set -euo pipefail` / comments, and
  2. at least one output-producing construct (cat / tee / echo / printf / heredoc),
     OR a delegation to a sibling script (e.g. `python solve.py`) that itself
     produces output - doc-refiling's solve.sh is a 7-line wrapper.

It follows one level of delegation into a referenced sibling script so a thin
wrapper is not a false positive.
"""
from __future__ import annotations

import re

from _lib import make_err, read_text, report, task_arg

# Commands that put text on stdout or into a file the grader path reads.
OUTPUT_CMD = re.compile(r"\b(cat|tee|echo|printf)\b")
HEREDOC = re.compile(r"<<-?\s*['\"]?[A-Za-z_]")
# Writing straight to a log/artifact path also counts even without an echo builtin.
WRITES_LOGS = re.compile(r"/(logs|app)/")
# A delegation to a sibling script, e.g. `python solve.py` or `bash run.sh`.
DELEGATE = re.compile(r"\b(?:python3?|bash|sh|uv run)\s+([\w./-]+\.(?:py|sh))\b")


def _has_output(text: str) -> bool:
    return (
        OUTPUT_CMD.search(text) is not None
        or HEREDOC.search(text) is not None
        or WRITES_LOGS.search(text) is not None
    )


def _body_lines(text: str) -> list[str]:
    return [
        ln for ln in text.splitlines()
        if ln.strip()
        and not ln.startswith("#!")
        and not ln.strip().startswith("#")
        and not re.match(r"^\s*set\s+-[a-z]+\b", ln)
    ]


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    solve = task / "solution" / "solve.sh"
    text = read_text(solve)
    if not text.strip():
        return report("check-solve-output", task, errors,
                      ["solve.sh empty; see check-required-files"])

    if not _body_lines(text):
        err(f"{solve}: no commands beyond the shebang/`set -euo pipefail`/comments. "
            "The oracle must produce an answer; an empty body scores 0.")

    if _has_output(text):
        return report("check-solve-output", task, errors, notes)

    # No direct output: allow a single level of delegation to a sibling script.
    delegated = False
    for m in DELEGATE.finditer(text):
        sibling = (solve.parent / m.group(1)).resolve()
        try:
            sibling.relative_to(solve.parent.resolve())
        except ValueError:
            continue
        if sibling.is_file() and _has_output(read_text(sibling)):
            delegated = True
            notes.append(f"solve.sh delegates to {m.group(1)}; output found there.")
            break

    if not delegated:
        err(f"{solve}: no output-producing command found (cat/tee/echo/printf/heredoc, "
            "a write to /logs or /app, or a delegation to a sibling script that produces "
            "output). A silent solve.sh hands the grader nothing.")

    return report("check-solve-output", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
