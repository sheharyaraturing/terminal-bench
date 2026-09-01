#!/usr/bin/env python3
"""The verifier runs code the submission wrote. It must not trust it.

At grade time the verifier holds a live OPENROUTER_API_KEY, the rubric that
decides the score, and network reach to the model gateway. It then starts a
server written by the thing being graded. Every one of those is reachable by
the submission unless the launch is deliberately locked down.

Three concrete exposures, in rough order of how quietly they fail:

  Credentials. A server started with the verifier's environment inherited can
  read OPENROUTER_API_KEY out of os.environ and post it anywhere it likes. This
  costs nothing to prevent (`env -i`, or an explicit env dict) and leaves no
  trace when it is missing.

  The rubric. A submission that can read /tests knows the exact criteria and
  fixtures it is about to be judged against, which turns a capability benchmark
  into an answer key.

  The host. A server running as root in the verifier container can rewrite the
  reward file, the rubric, or the judge's own configuration.

The current format handles all three (see tasks/bazaarbridge-marketplace's
tests/test.sh). The earlier browser-rubric shape grades in the shared agent
container and inherits os.environ, so its exposures are reported here too.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

# Ways to drop privileges before running submission code.
# An actual privilege-drop command. A bare uid elsewhere in the script — a
# `chown -R 65534:65534` on the copy, say — is not one, and matching it would
# wave through a server still started as root.
DROP_PRIVS = re.compile(r"\bsetpriv\b|\brunuser\b|\bgosu\b|\bsu-exec\b|"
                        r"\bsu\s+-|--reuid|--userspec|useradd[\s\S]{0,200}?USER\b|"
                        r"^\s*USER\s+\w", re.IGNORECASE | re.MULTILINE)
# Ways to start a process with a scrubbed environment.
CLEAN_ENV = re.compile(r"\benv\s+-i\b|env\s+--ignore-environment")


def task_arg() -> Path:
    if len(sys.argv) < 2:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <task-dir>")
    task = Path(sys.argv[1])
    if not task.is_dir():
        sys.exit(f"FATAL: {task} is not a directory")
    return task


def task_shape(task: Path) -> str:
    if sorted((task / "tests").glob("*/judge.toml")):
        return "dimensions"
    if (task / "tests" / "rubric" / "browser" / "browser.toml").is_file():
        return "browser-rubric"
    return "unknown"


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


def check_dimensions(task: Path, err, notes: list[str]) -> None:
    path = task / "tests" / "test.sh"
    sh = read_text(path)
    if not sh.strip():
        err(f"{path}: missing or empty (see check-required-files).")
        return

    if not CLEAN_ENV.search(sh):
        notes.append(
            f"{path}: starts the submitted server without scrubbing the "
            "environment. The verifier's environment holds OPENROUTER_API_KEY, so "
            "a server the submission wrote can read the key and send it anywhere, "
            "and nothing in the trial record would show it. `env -i` with an "
            "explicit allowlist (PATH, NODE_PATH, HOME, PORT) closes this. "
            "Advisory because it is a property of the harness pattern, not a "
            "defect in this task.")

    if not DROP_PRIVS.search(sh):
        notes.append(
            f"{path}: runs the submitted server as the verifier's own user. "
            "Dropping to an unprivileged uid (setpriv --reuid=65534 "
            "--regid=65534 --clear-groups) stops the app rewriting the reward "
            "file, the rubric, or the judge's configuration. Advisory: "
            "hardening, not a defect in this task.")

    # /tests holds the criteria the submission is about to be judged against.
    if not re.search(r"chmod\s+(-R\s+)?go-rwx\s+/tests|chmod\s+[0-7]*700\s+/tests", sh):
        notes.append("tests/test.sh does not restrict /tests. If the submitted "
                     "server can read it, the criteria and fixtures it is about to "
                     "be graded on are an open book. The current format does "
                     "`chmod -R go-rwx /tests`.")

    # A symlink under /app can point the copy — or the judge — at host paths.
    if not re.search(r"-type\s+l\b|islink|readlink", sh):
        notes.append("tests/test.sh does not reject symlinks under /app. A "
                     "submission can point one at the rubric or the reward file "
                     "and have the verifier follow it.")

    if not re.search(r"cp\s+-a?[rR]?\s*/app|cp\s+-a\s+/app", sh):
        notes.append("tests/test.sh appears to run the app from /app in place "
                     "rather than from a copy. Copying first keeps the graded "
                     "artifact intact for post-hoc review.")


def check_browser_rubric(task: Path, err, notes: list[str]) -> None:
    path = task / "tests" / "test.py"
    py = read_text(path)
    if not py.strip():
        err(f"{path}: missing or empty (see check-required-files).")
        return

    # os.environ here carries OPENROUTER_API_KEY and ANTHROPIC_AUTH_TOKEN,
    # because the judge is configured through [verifier.env].
    inherits = re.search(r"\{\s*\*\*\s*os\.environ|env\s*=\s*os\.environ", py)
    if inherits:
        notes.append(
            f"{path}: starts the submitted app with the verifier's environment "
            "inherited (`{**os.environ, ...}`). Harbor puts OPENROUTER_API_KEY "
            "and ANTHROPIC_AUTH_TOKEN there for the judge, so the app being "
            "graded can read them; whether that matters depends on whether "
            "grade-time has egress. Passing an explicit dict (PATH, HOME, PORT, "
            "HOST) removes the question. Advisory: this is the shape's "
            "shared-container pattern, not something this task did wrong.")

    if not re.search(r"preexec_fn|start_new_session|setsid|setuid|65534|nobody", py):
        notes.append("tests/test.py runs the submitted app as the verifier's own "
                     "user. This shape grades in the shared agent container, so "
                     "the app already has that access — but dropping privileges "
                     "before launch is still what stops it rewriting the reward "
                     "file.")


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    shape = task_shape(task)
    if shape == "dimensions":
        check_dimensions(task, err, notes)
    elif shape == "browser-rubric":
        check_browser_rubric(task, err, notes)
    else:
        err(f"{task}: no recognisable verifier (see check-required-files).")

    return report("check-verifier-sandbox", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
