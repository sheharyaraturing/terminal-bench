#!/usr/bin/env python3
"""Every /assets/... and /instructions/... path the brief names must exist AND
be COPYed into the image.

These paths are absolute container paths, so nothing in the repo resolves them
and nothing fails at build time. The agent discovers the mismatch at trial time
as a missing file it was told to read — which reads to the agent as its own
mistake, and lands as a low score for a task-authoring bug.

Two ways to get this wrong, both silent:
  1. instruction.md names /assets/artifacts/foo.json that is not in
     environment/assets/artifacts/.
  2. The file exists in environment/ but the Dockerfile never COPYs that tree,
     so it is present in the repo and absent from the container.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def join_continuations(text: str) -> list[str]:
    """Collapse shell/Dockerfile backslash continuations into single lines."""
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


def strip_comments(lines: list[str]) -> list[str]:
    """Drop whole-line # comments (Dockerfile/shell). Inline # is left alone:
    stripping it would mangle URLs and quoted strings."""
    return [ln for ln in lines if not ln.lstrip().startswith("#")]


def task_arg() -> Path:
    """The single positional argument: the task directory."""
    if len(sys.argv) < 2:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <task-dir>")
    task = Path(sys.argv[1])
    if not task.is_dir():
        sys.exit(f"FATAL: {task} is not a directory")
    return task
# Absolute container paths the brief hands the agent. The trailing character
# class stops the match before markdown punctuation (backticks, commas, periods).
PATH_RE = re.compile(r"/(assets|instructions)/[A-Za-z0-9._/-]*[A-Za-z0-9_/-]")


def _copied_roots(dockerfile: str) -> set[str]:
    """Image-root directories the Dockerfile COPYs into, e.g. {'assets'}.

    environment/ is the build context, so `COPY assets/ /assets/` maps
    environment/assets -> /assets.
    """
    roots: set[str] = set()
    for ln in strip_comments(join_continuations(dockerfile)):
        m = re.match(r"\s*(?:COPY|ADD)\s+(.*)", ln, re.IGNORECASE)
        if not m:
            continue
        args = [a for a in m.group(1).split() if not a.startswith("--")]
        if len(args) < 2:
            continue
        dest = args[-1].strip("\"'")
        if dest.startswith("/"):
            roots.add(dest.strip("/").split("/")[0])
    return roots


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    env_dir = task / "environment"
    dockerfile = read_text(env_dir / "Dockerfile")
    copied = _copied_roots(dockerfile)

    # Every file that ships the brief: the root instruction plus anything the
    # image copies into /instructions.
    sources = [task / "instruction.md"]
    instructions_dir = env_dir / "instructions"
    if instructions_dir.is_dir():
        sources += sorted(instructions_dir.rglob("*.md"))

    referenced: dict[str, list[str]] = {}
    for src in sources:
        for match in PATH_RE.finditer(read_text(src)):
            referenced.setdefault(match.group(0), []).append(str(src))

    if not referenced:
        notes.append("the brief names no /assets/ or /instructions/ paths. If seed "
                     "material ships in the image, the agent has no way to find it.")

    for ref, where in sorted(referenced.items()):
        root = ref.strip("/").split("/")[0]          # assets | instructions
        rel = ref.strip("/")                          # assets/artifacts/x.json
        on_disk = env_dir / rel

        if root not in copied:
            err(f"{env_dir / 'Dockerfile'}: never COPYs {root}/ into /{root}/, but "
                f"{where[0]} tells the agent to read {ref}. The file may exist in "
                "the repo and still be absent from the container.")

        # A bare directory reference (/assets/artifacts/) only has to exist.
        if ref.endswith("/") or on_disk.is_dir():
            if not on_disk.is_dir():
                err(f"{on_disk}: referenced as {ref} by {where[0]} but no such "
                    "directory under environment/.")
            elif not any(on_disk.iterdir()):
                err(f"{on_disk}: referenced as {ref} by {where[0]} but is empty.")
            continue

        if not on_disk.exists():
            err(f"{on_disk}: referenced as {ref} by {where[0]} but does not exist "
                "under environment/. The agent is told to read a file that is not "
                "in its container.")

    # The reverse direction: seed material nobody points at.
    assets_dir = env_dir / "assets"
    if assets_dir.is_dir():
        named = {r.rstrip("/") for r in referenced}
        for f in sorted(assets_dir.rglob("*")):
            if not f.is_file() or f.name.startswith("."):
                continue
            container_path = "/" + str(f.relative_to(env_dir))
            parent = "/" + str(f.parent.relative_to(env_dir))
            if container_path not in named and parent not in named:
                notes.append(f"{f} ships in the image at {container_path} but the "
                             "brief never names it or its directory — the agent has "
                             "to guess it is there.")

    return report("check-assets-referenced", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
