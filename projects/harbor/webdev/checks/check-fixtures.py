#!/usr/bin/env python3
"""Dockerfile COPY sources exist, assets are actually copied, and seeds parse.

Three build-time failures that each surface far from their cause:

  A COPY source that does not exist fails the image build minutes into a run,
  with an error naming a path inside a build context nobody is looking at.

  An assets/ directory the Dockerfile never copies is present in git and absent
  in the container. The task then runs with no seed data at all, and the agent
  is blamed for an empty app.

  A seed that does not parse crashes the app on first boot, after the agent has
  already spent its budget building against it.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

REMOTE_FETCH = re.compile(r"(?:git\s+clone|curl[^\n|]*\|\s*(?:ba)?sh|"
                          r"wget[^\n|]*\|\s*(?:ba)?sh)", re.IGNORECASE)


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

    env_dir = task / "environment"
    dockerfile = env_dir / "Dockerfile"
    text = read_text(dockerfile)
    lines = [ln for ln in join_continuations(text) if not ln.lstrip().startswith("#")]

    copies_assets = False
    for ln in lines:
        m = re.match(r"\s*(COPY|ADD)\s+(.*)", ln, re.IGNORECASE)
        if not m:
            continue
        args = [a for a in m.group(2).split() if not a.startswith("--")]
        if len(args) < 2:
            continue
        for src in args[:-1]:
            src = src.strip("\"'")
            # Remote URLs and build-arg interpolation are out of scope.
            if src.startswith(("http://", "https://", "$", "/")) or "${" in src:
                continue
            if src.rstrip("/").split("/")[0] == "assets":
                copies_assets = True
            if any(ch in src for ch in "*?["):
                if not list(env_dir.glob(src)):
                    err(f"{dockerfile}: {m.group(1).upper()} pattern {src!r} matches "
                        "nothing under environment/ — the image build fails.")
                continue
            if not (env_dir / src).exists():
                err(f"{dockerfile}: {m.group(1).upper()} source {src!r} does not "
                    f"exist at {env_dir / src}. The build context is environment/, "
                    "so this fails the image build minutes into a run.")

    assets = env_dir / "assets"
    if assets.is_dir() and any(assets.rglob("*")) and not copies_assets:
        err(f"{dockerfile}: environment/assets/ exists but nothing COPYs it into "
            "the image. The seed is in git and absent from the container, so the "
            "task runs with no data and the agent is blamed for an empty app.")

    if REMOTE_FETCH.search("\n".join(lines)):
        err(f"{dockerfile}: fetches and executes code from a live remote "
            "(git clone / curl | sh). The result changes without the task "
            "changing, and it cannot work in an offline build.")

    # Structured seeds must parse — the app reads them on first boot.
    if assets.is_dir():
        checked = 0
        for path in sorted(assets.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() == ".json":
                checked += 1
                try:
                    json.loads(read_text(path))
                except json.JSONDecodeError as exc:
                    err(f"{path}: invalid JSON - {exc}. The app crashes on first "
                        "boot, after the agent has already spent its budget.")
            elif path.suffix.lower() in (".csv", ".tsv"):
                checked += 1
                raw = read_text(path)
                try:
                    rows = list(csv.reader(io.StringIO(raw),
                                           delimiter="\t" if path.suffix == ".tsv" else ","))
                except csv.Error as exc:
                    err(f"{path}: unreadable CSV - {exc}")
                    continue
                if not rows or not rows[0] or not any(c.strip() for c in rows[0]):
                    notes.append(f"{path}: no obvious header row. Fine for a "
                                 "positional loader; empty data for one that reads "
                                 "by column name.")
        if checked:
            notes.append(f"parsed {checked} structured seed file(s).")

    return report("check-fixtures", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
