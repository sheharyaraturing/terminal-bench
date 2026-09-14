#!/usr/bin/env python3
"""A shipped dependency manifest must name only pre-installed packages.

The prompt tells the agent its dependencies are already available and that it
must not install anything. If the reference's package.json (or
requirements.txt) names a library the agent image never installed, the task is
not hard — it is impossible: the agent cannot fetch it under no-network and
cannot build without it.

N/A when the solution ships no manifest, which is the normal case for a static
page or a client-only game.
"""
from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

# Node ships these; no image has to install them.
NODE_BUILTINS = {"node:sqlite", "node:fs", "node:path", "node:http", "fs", "path",
                 "http", "crypto", "url", "os", "util", "events", "stream"}


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


def agent_is_offline(task: Path) -> bool:
    """True when the agent phase cannot reach a package registry."""
    try:
        with (task / "task.toml").open("rb") as fh:
            cfg = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return (cfg.get("environment") or {}).get("network_mode") in ("no-network", "none")


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    offline = agent_is_offline(task)
    dockerfile = read_text(task / "environment" / "Dockerfile")
    manifests = [p for p in (task / "solution").rglob("package.json")
                 if "node_modules" not in p.parts]
    manifests += [p for p in (task / "solution").rglob("requirements.txt")]

    if not manifests:
        print(f"NOTE {task}: the reference ships no dependency manifest; nothing to "
              "cross-check against the image.")
        print(f"check-package-manifest-deps-preinstalled: OK ({task})")
        return 0

    for manifest in sorted(manifests):
        deps: list[str] = []
        if manifest.name == "package.json":
            try:
                data = json.loads(read_text(manifest))
            except json.JSONDecodeError as exc:
                err(f"{manifest}: not valid JSON - {exc}")
                continue
            # Runtime only: devDependencies are build tooling, and a
            # build-at-launch task installs them itself.
            deps = list((data.get("dependencies") or {}).keys())
        else:
            for line in read_text(manifest).splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    deps.append(re.split(r"[=<>!~\[]", line)[0].strip())

        for dep in sorted(deps):
            if dep in NODE_BUILTINS or dep.startswith("node:"):
                continue
            if dep in dockerfile:
                continue
            message = (f"{manifest}: names the runtime dependency {dep!r}, which "
                       f"{task}/environment/Dockerfile never installs.")
            if offline:
                notes.append(message + " The agent phase has no network, so unless "
                             "it arrives transitively or under another name the "
                             "task is unsolvable rather than difficult.")
            else:
                notes.append(message + " The agent phase has network and the oracle "
                             "runs npm install, so this resolves at trial time — but "
                             "it makes every run depend on the registry being up.")

    return report("check-package-manifest-deps-preinstalled", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
