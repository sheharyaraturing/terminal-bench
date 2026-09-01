#!/usr/bin/env python3
"""The interface strings that must agree across the task's files.

This is the highest-value mechanical check unique to this format, because its
failure mode is invisible and one-sided: a drifted port or a health endpoint
that only the verifier knows about zeroes every correct, instruction-following
agent, while the author's own reference — which happens to implement the hidden
path — passes. The task then looks hard rather than broken.

Four rows, all compared as literal strings. Nothing here interprets the app:

  1. Port.          test.sh's port == every judge prompt URL's port ==
                    the port instruction.md names.
  2. App entry.     A file test.sh launches must be named (or implied) by
                    instruction.md and created by solve.sh.
  3. Liveness path. A probe path other than "/" must appear in instruction.md,
                    or it is a contract only the grader knows.
  4. Injected env.  A KEY=value test.sh puts in the app's environment should
                    appear in the prompt as that value or that variable name.

Rows whose inputs are absent are skipped, so a static page with no env and no
health path is simply quiet here.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

PORT_RE = re.compile(r"(?<!\d)(\d{4,5})(?!\d)")
URL_PORT_RE = re.compile(r"https?://(?:localhost|127\.0\.0\.1):(\d{2,5})")
# The launcher's own idea of the port, in the forms both shapes write it:
#   shell:  PORT="3000"   PORT=3000   --port 3000
#   python: os.environ.get("PORT", "3000")   getenv("PORT", 3000)
# A python launcher never matches the shell form, and missing it silently
# skipped the whole port comparison for the browser-rubric shape.
ENV_PORT_RE = re.compile(
    r"\bPORT\s*=\s*[\"']?(\d{2,5})\b"
    r"|[\"']PORT[\"']\s*,\s*[\"']?(\d{2,5})[\"']?"
    r"|--port[= ]\s*[\"']?(\d{2,5})",
    re.IGNORECASE)
# A file the launcher actually runs.
ENTRY_RE = re.compile(
    r"\b(?:node|python3?|deno|bun|ruby|php)\s+"           # the runtime
    r"(?:-[-\w]+\s+)*"                                    # flags
    r"[\"']?(?:\$\{?[A-Za-z_][A-Za-z0-9_]*\}?)?"          # optional $VAR prefix
    r"(?:[/A-Za-z0-9._-]*/)?"                              # optional directory
    r"([A-Za-z0-9_-]+\.(?:js|mjs|cjs|ts|py|rb|php))\b")    # the filename
# urlopen("http://127.0.0.1:3000/api/health") / curl .../healthz
PROBE_PATH_RE = re.compile(r"https?://(?:localhost|127\.0\.0\.1):\d{2,5}(/[A-Za-z0-9._/-]*)")
# Environment injected into the app's process: `DB_PATH="..."` on a launch line.
INJECTED_ENV_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]{2,})=\"?([^\"\s]*)\"?\s*\\?\s*$",
                             re.MULTILINE)
# Variables the launcher sets for its own bookkeeping, not the app's contract.
IGNORED_ENV = {"PATH", "HOME", "NODE_PATH", "LOG_DIR", "APP_PID", "APP_COPY",
               "READY", "DEBIAN_FRONTEND", "PYTHONUNBUFFERED", "TZ", "LANG",
               "VERIFIER_LOG_DIR", "NODE_ENV", "HOST"}


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


def load_toml(path: Path, err) -> dict:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        err(f"{path}: not valid TOML - {e}")
    return {}


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


def judge_prompts(task: Path, err) -> dict[str, str]:
    """dimension -> prompt text, for whichever shape the task uses."""
    out: dict[str, str] = {}
    for p in sorted((task / "tests").glob("*/judge.toml")):
        template = (load_toml(p, err).get("judge") or {}).get("prompt_template")
        if isinstance(template, str):
            out[p.parent.name] = template
    if out:
        return out
    rdir = task / "tests" / "rubric" / "browser"
    cfg = load_toml(rdir / "browser.toml", err)
    name = (cfg.get("judge") or {}).get("prompt_template") or "prompt.md"
    text = read_text(rdir / name)
    if text:
        out["browser"] = text
    return out


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    instruction = read_text(task / "instruction.md")
    launcher_path = task / "tests" / "test.sh"
    launcher = read_text(launcher_path)
    # The browser-rubric shape launches from test.py instead.
    if (task / "tests" / "test.py").is_file():
        launcher += "\n" + read_text(task / "tests" / "test.py")
    solve = read_text(task / "solution" / "solve.sh")
    prompts = judge_prompts(task, err)

    # ---- 1. port -----------------------------------------------------------
    launcher_ports = {p for groups in ENV_PORT_RE.findall(launcher)
                      for p in (groups if isinstance(groups, tuple) else (groups,))
                      if p}
    launcher_ports |= set(URL_PORT_RE.findall(launcher))
    prompt_ports: dict[str, set[str]] = {
        d: set(URL_PORT_RE.findall(t)) for d, t in prompts.items()}
    all_prompt_ports = set().union(*prompt_ports.values()) if prompt_ports else set()

    if launcher_ports and all_prompt_ports:
        mismatched = {d: p for d, p in prompt_ports.items()
                      if p and not (p & launcher_ports)}
        if mismatched:
            err(f"{launcher_path}: binds/probes port(s) {sorted(launcher_ports)} but "
                f"judge prompt(s) point at a different port: "
                f"{ {d: sorted(p) for d, p in mismatched.items()} }. The judge opens "
                "a dead socket while the app listens elsewhere, and every criterion "
                "in that dimension fails for a reason the submission cannot see.")
    if launcher_ports and instruction:
        instruction_ports = set(PORT_RE.findall(instruction))
        if instruction_ports and not (instruction_ports & launcher_ports):
            err(f"{task}/instruction.md: names port(s) {sorted(instruction_ports)} "
                f"but the verifier uses {sorted(launcher_ports)}. An agent that "
                "follows the prompt binds a port nothing connects to.")
        elif not instruction_ports:
            notes.append(f"instruction.md names no port, but the verifier expects "
                         f"{sorted(launcher_ports)}. Unless the app is served as "
                         "static files, the prompt should state the port.")

    # ---- 2. app entry ------------------------------------------------------
    # The launcher also runs its own helpers (test.py, a urllib one-liner);
    # those are grader machinery, not the submitted app's entrypoint.
    GRADER_OWN = {"test.py", "test.sh", "solve.py"}
    entries = {e for e in ENTRY_RE.findall(launcher) if e not in GRADER_OWN}
    for entry in sorted(entries):
        if instruction and entry not in instruction:
            notes.append(f"tests/test.sh launches {entry!r} but instruction.md never "
                         "names it. Unless the start command is stated some other "
                         "way, the agent has to guess the entrypoint filename.")
        shipped = any(p.name == entry for p in (task / "solution").rglob("*")
                      if p.is_file())
        if solve and entry not in solve and not shipped:
            err(f"{task}/solution/solve.sh: the verifier launches {entry!r}, but the "
                "oracle neither names it nor ships a file with that name under "
                "solution/ — the reference cannot start, so the task has never "
                "been validated end to end.")

    # ---- 3. liveness path --------------------------------------------------
    probe_paths = {p for p in PROBE_PATH_RE.findall(launcher) if p not in ("/", "")}
    for probe in sorted(probe_paths):
        if instruction and probe not in instruction:
            # Advisory, not a failure. The string gap is certain; the harm is
            # not. Plenty of agents add a health endpoint by convention, and an
            # author may reasonably rely on that. Blocking a task on a
            # convention call is worse than surfacing it for a human.
            notes.append(f"{launcher_path}: waits for {probe!r} before grading, "
                         "but instruction.md never mentions it. An agent that "
                         "builds exactly what was asked may not serve this path; "
                         "if it does not, the readiness gate times out and the "
                         "whole run scores 0 while the reference passes. Either "
                         "state the path in the prompt or poll one the prompt "
                         "already guarantees.")

    # ---- 4. injected environment -------------------------------------------
    injected = {k: v for k, v in INJECTED_ENV_RE.findall(launcher)
                if k not in IGNORED_ENV}
    for key, value in sorted(injected.items()):
        if not instruction:
            break
        if key in instruction or (value and value in instruction):
            continue
        notes.append(f"tests/test.sh injects {key}={value!r} into the app's "
                     "environment, but instruction.md names neither the variable "
                     "nor the value. If the app is expected to honour it, the "
                     "prompt has to say so.")

    return report("check-runtime-contract-strings", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
