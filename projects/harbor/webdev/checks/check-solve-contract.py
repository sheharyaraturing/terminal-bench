#!/usr/bin/env python3
"""solution/solve.sh: the oracle must install an app the verifier can grade.

An oracle that cannot score means the task has never been validated end to end,
and a 0.0 for install reasons reads as "the rubric is too hard" rather than
"the oracle broke". The strongest form of this check is a cross-check: the
verifier refuses to grade unless certain files exist under /app, so the oracle
must be the thing that creates exactly those.

What the oracle is allowed to do differs by shape. The current format runs the
agent phase offline against dependencies already baked into the image, so its
oracle installs nothing and builds nothing. The earlier shape has network and a
frontend to compile, so its oracle must run npm and a build.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

# `[[ ! -f /app/server.js || ! -f /app/public/index.html ]]` and friends: the
# paths the verifier insists on before it will grade anything.
APP_GUARD_RE = re.compile(r"-[ef]\s+(/app/[A-Za-z0-9._/-]+)")


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


def strip_comments(lines: list[str]) -> list[str]:
    return [ln for ln in lines if not ln.lstrip().startswith("#")]


def shell_hygiene(path: Path, err) -> None:
    """Parse and line-ending checks shared by every shell entrypoint.

    A CRLF line ending is the nastiest of these: the shell reads
    `set -euo pipefail\r` as a command named `pipefail\r`, the script dies on
    line 2, and the failure surfaces as a missing reward file that names
    nothing. It is invisible in every editor and in most diffs.
    """
    raw = path.read_bytes() if path.is_file() else b""
    if b"\r\n" in raw:
        line = raw.split(b"\r\n")[0][:60].decode("utf-8", "replace")
        err(f"{path}: has CRLF line endings (first: {line!r}...). The shell reads "
            "the carriage return as part of the command, so the script dies "
            "immediately and the run reports a missing reward rather than an "
            "error anyone can act on. Convert to LF.")
    if raw and not raw.startswith(b"#!"):
        err(f"{path}: no shebang line.")
    proc = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        err(f"{path}: is not valid bash - {detail[0] if detail else 'parse error'}")


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

    path = task / "solution" / "solve.sh"
    text = read_text(path)
    if not text.strip():
        err(f"{path}: missing or empty — the task has no oracle.")
        return report("check-solve-contract", task, errors, notes)

    code = "\n".join(strip_comments(join_continuations(text)))
    shape = task_shape(task)

    shell_hygiene(path, err)

    if not re.search(r"^\s*set\s+-[a-zA-Z]*e", code, re.MULTILINE):
        notes.append(f"{path}: no `set -e`. A failed copy or build then leaves a "
                     "half-installed app and the oracle scores 0.0 with a green "
                     "exit code, which reads as a hard rubric rather than a broken "
                     "oracle.")

    if not re.search(r"/app\b", code):
        err(f"{path}: never writes to /app, which is where the verifier looks for "
            "the application.")

    # The verifier owns these; an oracle that touches them is grading itself.
    if re.search(r"/logs/verifier", code):
        err(f"{path}: writes into /logs/verifier, the verifier's own output "
            "directory — an oracle that writes a reward there scores itself.")
    if re.search(r"(^|\s)(cp|mv|rm|>)\s[^\n]*\s/tests(/|\s|$)", code, re.MULTILINE):
        err(f"{path}: writes into /tests, which holds the grading code.")
    if re.search(r">\s*/solution/|(cp|mv|rm)\s[^|]*\s/solution/\S*\s*$", code,
                 re.MULTILINE):
        err(f"{path}: appears to write into /solution, which is mounted read-only.")

    # The reference must build from what the image already provides — it is
    # held to the same no-install rule the agent is.
    for fetch in ("curl", "wget", "npm install", "npm ci", "pip install",
                  "pip3 install", "apt-get install"):
        if re.search(rf"(?<![\w-]){re.escape(fetch)}(?![\w-])", code) and \
                shape == "dimensions":
            err(f"{path}: runs {fetch!r}. The agent phase has no network and the "
                "prompt says dependencies are already available; the reference "
                "must not need a registry either.")

    if re.search(r"\b(pkill|killall)\b", code):
        err(f"{path}: runs pkill/killall, which can kill the agent session and the "
            "harness alongside the app.")
    if re.search(r"NODE_ENV\s*=\s*production", code):
        err(f"{path}: sets NODE_ENV=production. npm's default --omit becomes "
            "\"dev\", silently skipping the devDependencies a frontend build needs.")

    # ---- the cross-check: does the oracle create what the verifier demands? --
    guards = sorted(set(APP_GUARD_RE.findall(read_text(task / "tests" / "test.sh"))))
    for required in guards:
        basename = required.rsplit("/", 1)[-1]
        # Accept either the full path or the basename: `cp x /app/server.js` and
        # `cp -R ./. /app/` with a matching source both satisfy the guard.
        if required not in code and basename not in code:
            err(f"{path}: tests/test.sh refuses to grade unless {required} exists, "
                f"but the oracle never creates it. The oracle would score 0.0 "
                "without a single criterion being judged, and the task would look "
                "impossible rather than broken.")
    if guards:
        notes.append(f"verifier requires under /app: {', '.join(guards)}.")

    # ---- shape-specific expectations ---------------------------------------
    if shape == "browser-rubric":
        # Both of these are how the two existing tasks happen to be written,
        # not a contract: `$(dirname "$0")` is an equally valid way to find the
        # reference, and a task with no manifest installs nothing.
        if not re.search(r"/solution|dirname", code):
            notes.append(f"{path}: never references /solution or $(dirname \"$0\"); "
                         "confirm it can locate the reference at oracle time.")
        manifest = any((task / "solution").rglob("package.json"))
        if manifest and not re.search(r"\bnpm\s+(ci|install)\b", code):
            notes.append(f"{path}: ships a package.json but never runs npm "
                         "install/ci; confirm node_modules reaches /app.")
        if not re.search(r"npm\s+run\s+build|npm\s+build", code):
            notes.append("solve.sh runs no frontend build; both tasks of this shape "
                         "compile the UI before launch, and the verifier will find "
                         "no dist/index.html.")
    elif shape == "dimensions":
        # The agent phase is offline here, so a registry fetch cannot succeed.
        if re.search(r"\bnpm\s+(ci|install)\b(?![^\n]*--offline)", code):
            notes.append("solve.sh runs npm install. The current format bakes "
                         "dependencies into the image and runs the agent phase with "
                         "no network — confirm this resolves offline, or drop it.")

    return report("check-solve-contract", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
