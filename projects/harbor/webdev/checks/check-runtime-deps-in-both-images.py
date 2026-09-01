#!/usr/bin/env python3
"""Runtime dependencies must exist in the verifier image, not just the agent's.

This is the two-environment trap as a set difference. The agent builds in
environment/Dockerfile's image; the app is *started and graded* in the
verifier's, which is a different image with no network. A library only the
agent image installs is simply gone at grade time: the app dies on
`Cannot find module 'express'`, every dimension scores 0, and the log reads
like a bad submission rather than a missing line in a Dockerfile.

Build-only tooling (git, compilers, curl) is deliberately not required in the
verifier — it is needed to produce the app, not to run it.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

# Packages that exist to build or fetch, never to be imported at runtime.
BUILD_ONLY = {
    "git", "curl", "wget", "gnupg", "ca-certificates", "build-essential",
    "python3-pip", "python3-venv", "make", "gcc", "g++", "pkg-config",
    "unzip", "xz-utils", "procps", "psmisc", "iproute2", "tmux", "sqlite3",
    "util-linux", "npm", "yarn", "pnpm", "vite", "tailwindcss", "postcss",
    "autoprefixer", "esbuild", "webpack", "typescript",
}
# The judge's own toolchain belongs only in the verifier image.
VERIFIER_ONLY = re.compile(r"playwright|codex|claude-code|rewardkit|openai|"
                           r"python-dotenv|pyyaml", re.IGNORECASE)


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


def npm_packages(text: str) -> dict[str, str]:
    """package name -> version string, from every npm install line."""
    found: dict[str, str] = {}
    for line in join_continuations(text):
        if line.lstrip().startswith("#"):
            continue
        for segment in re.split(r"&&|\|\||;", line):
            m = re.match(r"\s*(?:RUN\s+)?npm\s+(?:install|i|add)\b(.*)", segment)
            if not m:
                continue
            for tok in m.group(1).split():
                if tok.startswith("-") or tok.startswith(">"):
                    continue
                if not re.match(r"^@?[a-z0-9]", tok, re.IGNORECASE):
                    continue
                name, _, version = tok.rpartition("@")
                if not name:  # unscoped and unpinned: "express"
                    name, version = tok, ""
                found[name] = version
    return found


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    agent_path = task / "environment" / "Dockerfile"
    verifier_path = task / "tests" / "Dockerfile"
    if not verifier_path.is_file():
        print(f"NOTE {task}: no tests/Dockerfile — the verifier shares the agent's "
              "image, so there is no second environment to diverge from.")
        print(f"check-runtime-deps-in-both-images: OK ({task})")
        return 0

    agent = npm_packages(read_text(agent_path))
    verifier = npm_packages(read_text(verifier_path))

    for name, version in sorted(agent.items()):
        if name in BUILD_ONLY or VERIFIER_ONLY.search(name):
            continue
        if name not in verifier:
            notes.append(
                f"{verifier_path}: {name!r} is installed in the agent image but "
                "not here. If the app imports it at start-up it will not resolve "
                "at grade time. Advisory because build-only versus runtime cannot "
                "be told apart from a package name alone.")
        elif version and verifier[name] and verifier[name] != version:
            notes.append(f"{name} is {version} in the agent image and "
                         f"{verifier[name]} in the verifier image. The app is built "
                         "against one and run against the other.")

    if not agent:
        notes.append("the agent image installs no npm packages; nothing to compare. "
                     "Fine for a static or client-only app.")

    return report("check-runtime-deps-in-both-images", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
