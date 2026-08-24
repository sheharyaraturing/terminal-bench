#!/usr/bin/env python3
"""solution/solve.sh must emit an answer the judge can actually see.

Harbor's OracleAgent captures solve.sh's stdout into /logs/agent/oracle.txt, and
tests/test.sh bridges that (or a directly-written final_answer.txt) to the path
[judge].files reads. A solve.sh that computes quietly, or writes the answer to a
path nobody reads, scores the oracle ~0 however correct it is.

This check is intentionally shallow - it does not run the script. It requires:
  1. non-trivial content beyond the shebang / `set -euo pipefail` / comments, and
  2. at least one output-producing construct (cat / tee / echo / printf / heredoc),
     so something reaches stdout or /logs/agent/.

check-oracle-not-parrot covers the orthogonal "is the answer a real answer"
question; this covers "does an answer reach the judge at all".
"""
from __future__ import annotations

import re

from _lib import make_err, read_text, report, task_arg

# Commands that put text on stdout or into a file the judge path reads.
OUTPUT_CMD = re.compile(r"\b(cat|tee|echo|printf)\b")
HEREDOC = re.compile(r"<<-?\s*['\"]?[A-Za-z_]")
# Writing straight to the bridged path also counts even without an echo builtin.
WRITES_LOGS = re.compile(r"/logs/agent/(final_answer|oracle)\.txt")


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    err = make_err(errors)

    solve = task / "solution" / "solve.sh"
    text = read_text(solve)
    if not text.strip():
        # check-required-files / check-oracle-not-parrot report the empty file.
        return report("check-solve-output", task, errors,
                      ["solve.sh empty; see check-required-files"])

    # Non-trivial body: drop shebang, `set ...`, comments, and blank lines.
    body = [
        ln for ln in text.splitlines()
        if ln.strip()
        and not ln.startswith("#!")
        and not ln.strip().startswith("#")
        and not re.match(r"^\s*set\s+-[a-z]+\b", ln)
    ]
    if not body:
        err(f"{solve}: no commands beyond the shebang/`set -euo pipefail`/comments. "
            "The oracle must emit an answer; an empty body scores 0.")

    produces_output = (
        OUTPUT_CMD.search(text) is not None
        or HEREDOC.search(text) is not None
        or WRITES_LOGS.search(text) is not None
    )
    if not produces_output:
        err(f"{solve}: no output-producing command found (cat/tee/echo/printf/heredoc, "
            "or a write to /logs/agent/final_answer.txt|oracle.txt). Harbor's OracleAgent "
            "only captures stdout into oracle.txt; a silent solve.sh hands the judge nothing.")

    return report("check-solve-output", task, errors, [])


if __name__ == "__main__":
    raise SystemExit(main())
