#!/usr/bin/env python3
"""The scripts that run during a trial must not depend on the outside world.

tests/test.sh and solution/solve.sh execute while a trial is in flight, inside
images that were built earlier and — for the agent phase — with no network at
all. Anything they fetch, resolve, or read off the host makes the result depend
on something other than the task:

  A network fetch at trial time turns a registry outage into a scored 0.0, and
  a package that moved into a different score for the same submission.

  An unpinned install resolves to whatever is newest that day. The task did not
  change; what it ran did.

  A bare `nproc` reads the host's CPU count. The same submission then builds
  with -j2 on one machine and -j64 on another, and a flaky parallel build looks
  like a flaky submission.

These rules used to come from the repo-root common set (check-nproc.sh,
check-pip-pinning.sh, check-trial-network-fetch.sh, check-verifier-tooling-
baked.sh). That set is no longer run here — it also carries rules that
contradict this project's severity policy — so the parts worth keeping live in
this check instead.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

# Fetching from the network mid-trial.
FETCH = re.compile(
    r"\b(?:curl|wget)\b(?![^\n|]*\b(?:127\.0\.0\.1|localhost)\b)"
    r"|\bgit\s+clone\b"
    r"|\bpip3?\s+install\b(?![^\n]*--no-index)"
    r"|\bnpm\s+(?:install|ci|add)\b"
    r"|\buvx?\b[^\n]*--with\b")
# Reading the host's CPU count instead of a fixed value.
BARE_NPROC = re.compile(r"(?<![\w-])nproc(?![\w-])")
# Verifier test tooling installed at trial time rather than baked into the image.
TRIAL_TOOLING = re.compile(r"\b(?:pytest|pytest-json-ctrf|playwright|rewardkit)\b"
                           r"[^\n]*\b(?:install|--with)\b"
                           r"|\b(?:install|--with)\b[^\n]*"
                           r"\b(?:pytest|pytest-json-ctrf|playwright)\b")


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


def join_continuations(text: str) -> list[str]:
    out: list[str] = []
    buf = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        out.append(buf + line)
        buf = ""
    if buf:
        out.append(buf)
    return out


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

    for rel in ("tests/test.sh", "solution/solve.sh"):
        path = task / rel
        text = read_text(path)
        if not text.strip():
            continue  # check-required-files reports a missing script
        for i, line in enumerate(join_continuations(text), 1):
            if line.lstrip().startswith("#"):
                continue

            m = FETCH.search(line)
            if m:
                err(f"{path}:{i}: fetches at trial time ({m.group(0).strip()!r}). "
                    "The images are built ahead of the trial and the agent phase "
                    "has no network, so this either fails outright or makes the "
                    "score depend on a registry being up that day.")

            if BARE_NPROC.search(line):
                err(f"{path}:{i}: uses bare `nproc`, which reads the host's CPU "
                    "count. The same submission then builds differently on "
                    "different machines, and a flaky parallel build reads as a "
                    "flaky submission. Use a fixed number.")

            if TRIAL_TOOLING.search(line):
                err(f"{path}:{i}: installs verifier tooling at trial time. The "
                    "verifier runs in the image built from tests/Dockerfile — bake "
                    "it there, so grading does not depend on the network and the "
                    "version cannot drift between runs.")

    return report("check-trial-time-hermetic", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
