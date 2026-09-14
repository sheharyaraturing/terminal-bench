#!/usr/bin/env python3
"""solution/app/APP_MANIFEST.md must carry the start command the verifier parses.

tests/test.py finds the app's start command by pulling the first ```bash start
fenced block out of APP_MANIFEST.md, and silently falls back to a hard-coded
default when there is none. For the golden solution that fallback is a coin
flip: `npm start` when the app has no start script, or `npm run build && node
src/index.js` when the entrypoint lives elsewhere. Either way the app never
becomes healthy, the judge never gets a page, and the oracle scores 0.0 with no
error that points at the manifest.

The manifest is also the agent's contract: the task tells it to describe its
own API shape there, because no endpoint paths are prescribed anywhere.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

# APP_MANIFEST.md's start command fence — the exact shape tests/test.py parses.
START_FENCE_RE = re.compile(r"```bash start\s*\n(.*?)```", re.DOTALL)


def task_arg() -> Path:
    """The single positional argument: the task directory."""
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


def make_err(errors: list[str]):
    def err(msg: str) -> None:
        errors.append(msg)

    return err


def report(name: str, task: Path, errors: list[str], notes: list[str]) -> int:
    """Print a uniform per-check report and return the process exit code."""
    for n in notes:
        print(f"NOTE {task}: {n}")
    if errors:
        for e in errors:
            print(f"FAIL {e}")
        print(f"{name}: {len(errors)} problem(s)")
        return 1
    print(f"{name}: OK ({task})")
    return 0

# The judge is told (in prompt.md) to treat the manifest as untrusted content
# from the submission. The GOLDEN manifest must still not read like grader
# instructions.
INJECTION_RE = re.compile(
    r"\b(you are the|as the (judge|grader|verifier)|mark this|award (full|the) "
    r"(score|credit)|pass this criterion|ignore (the )?(previous|above))\b",
    re.IGNORECASE,
)


def task_shape(task: Path) -> str:
    if sorted((task / "tests").glob("*/judge.toml")):
        return "dimensions"
    if (task / "tests" / "rubric" / "browser" / "browser.toml").is_file():
        return "browser-rubric"
    return "unknown"


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    # Only the browser-rubric shape discovers its start command from a manifest.
    # The current format states the entrypoint in instruction.md and enforces it
    # in tests/test.sh, which check-solve-contract.py cross-checks instead.
    if task_shape(task) != "browser-rubric":
        print(f"NOTE {task}: no APP_MANIFEST start-command contract in this shape; "
              "the entrypoint is fixed by instruction.md and tests/test.sh.")
        print(f"check-app-manifest: OK ({task})")
        return 0

    path = task / "solution" / "app" / "APP_MANIFEST.md"
    text = read_text(path)
    if not text.strip():
        err(f"{path}: missing or empty. tests/test.py parses the app's start "
            "command out of it and falls back to a hard-coded default when it is "
            "absent — the golden app then never starts and the oracle scores 0.0.")
        return report("check-app-manifest", task, errors, notes)

    blocks = START_FENCE_RE.findall(text)
    if not blocks:
        err(f"{path}: no ```bash start fenced block. That exact fence (```bash "
            "start) is what tests/test.py's _START_BLOCK_RE matches; a plain "
            "```bash or ```sh fence is not recognised and the verifier silently "
            "uses its default start command instead.")
    else:
        if len(blocks) > 1:
            notes.append(f"{len(blocks)} ```bash start blocks; tests/test.py uses the "
                         "FIRST and ignores the rest.")
        command = blocks[0].strip()
        if not command:
            err(f"{path}: the ```bash start block is empty.")
        # A start command that backgrounds itself returns immediately; test.py
        # then treats a dead process as a running app and waits out the health
        # timeout.
        if re.search(r"&\s*$", command) or "nohup" in command:
            err(f"{path}: the start command backgrounds itself ({command!r}). "
                "tests/test.py manages the process itself and kills it by pid; a "
                "command that returns immediately orphans the server and the "
                "health wait times out.")
        # Both shipped tasks warn about this in instruction.md; the golden
        # manifest must not model the behaviour it warns against.
        if re.search(r"pkill|killall", command):
            err(f"{path}: the start command runs pkill/killall, which can kill the "
                "agent session and the verifier alongside the app.")

    # The manifest is the only place the app's own API shape is written down.
    if not re.search(r"http://(localhost|127\.0\.0\.1)", text):
        notes.append("APP_MANIFEST.md does not state the base URL the app serves on. "
                     "It is the agent's contract for describing its own choices, "
                     "since no endpoint paths are prescribed anywhere in the task.")

    if INJECTION_RE.search(text):
        err(f"{path}: contains grader-directed language. prompt.md tells the judge "
            "to treat APP_MANIFEST.md as untrusted content from the submission; "
            "the golden manifest must not model an injection attempt.")

    return report("check-app-manifest", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
