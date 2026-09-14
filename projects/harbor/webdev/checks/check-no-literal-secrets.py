#!/usr/bin/env python3
"""No live credential may be committed in the task tree.

A provider key checked into git is a real credential in a real repository, and
it stays live after the commit is reverted. This is the cheap mechanical sweep:
key shapes, PEM blocks, and env values in task.toml that should be ${VAR}
templates.

Demo passwords in instruction.md are explicitly fine — they are the product
interface, and the judge needs them. Whether synthetic names and addresses are
appropriate is a rubric judgment, not a grep.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

SECRET_SHAPES = [
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}"), "an OpenAI-style secret key"),
    (re.compile(r"\bsk-or-v1-[A-Za-z0-9]{20,}"), "an OpenRouter key"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"), "a GitHub token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "an AWS access key id"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"), "a Google API key"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "a Slack token"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
     "a private key block"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\."), "a JWT"),
]
# task.toml env keys whose value must be a ${VAR} template, never a literal.
SECRET_KEY_RE = re.compile(r"key|token|secret|password|credential", re.IGNORECASE)
TEMPLATE_RE = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".woff", ".woff2",
                   ".ttf", ".otf", ".mp3", ".mp4", ".wasm", ".zip", ".db",
                   ".sqlite", ".sqlite3", ".ico", ".pdf"}


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

    for path in sorted(task.rglob("*")):
        if not path.is_file() or path.suffix.lower() in BINARY_SUFFIXES:
            continue
        if "node_modules" in path.parts or path.name == "package-lock.json":
            continue
        text = read_text(path)
        if not text:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for pattern, what in SECRET_SHAPES:
                if pattern.search(line):
                    err(f"{path}:{i}: looks like {what} committed in the task tree. "
                        "A key in git stays live after the commit is reverted — "
                        "rotate it, then replace the value with a ${VAR} template.")

    # task.toml env values: a literal here is both a leak and a broken run on
    # any machine that does not happen to share the author's account.
    toml_path = task / "task.toml"
    try:
        with toml_path.open("rb") as fh:
            cfg = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        cfg = {}
    for section in (("verifier", "env"), ("agent", "env"), ("environment", "env")):
        block = cfg
        for key in section:
            block = (block or {}).get(key) if isinstance(block, dict) else None
        if not isinstance(block, dict):
            continue
        for key, value in block.items():
            if not SECRET_KEY_RE.search(key) or not isinstance(value, str):
                continue
            if value == "" or TEMPLATE_RE.match(value):
                continue
            err(f"{toml_path}: [{'.'.join(section)}].{key} holds a literal value "
                f"({value[:12]!r}…) rather than a ${{VAR}} template. Secrets must be "
                "injected at run time, not committed.")

    return report("check-no-literal-secrets", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
