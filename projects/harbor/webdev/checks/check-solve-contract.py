#!/usr/bin/env python3
"""solution/solve.sh: the oracle must install an app the verifier can grade.

An oracle that cannot score means the task has never been validated end to end,
and a 0.0 for install reasons reads as "the rubric is too hard" rather than
"the oracle broke". The strongest form of this check is a cross-check: the
verifier refuses to grade unless certain files exist under /app, so the oracle
must be the thing that creates exactly those.

What the oracle is allowed to do differs by shape, and — for the offline-install
rule below — by this task's actual `[environment].network_mode`. A task whose
agent phase is genuinely offline must have an oracle that installs nothing at
solve time either; a task with network access (this project's default) is free
to run npm/pip at solve time, so that is only ever a NOTE, never a FAIL.
"""
from __future__ import annotations

import re
import shlex
import subprocess
import sys
import tomllib
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
    # Resolve to an absolute path: the guard cross-check anchors copy sources
    # at "<task>/solution", and a relative root would be prepended to itself
    # when a $(dirname "$0") token is substituted into it.
    return task.resolve()


def task_shape(task: Path) -> str:
    if sorted((task / "tests").glob("*/judge.toml")):
        return "dimensions"
    if (task / "tests" / "rubric" / "browser" / "browser.toml").is_file():
        return "browser-rubric"
    return "unknown"


def agent_is_offline(task: Path) -> bool:
    """True when the agent phase (and so the oracle, held to the same rule)
    cannot reach a package registry. Matches the sibling checks' helper of the
    same name — this project's default is `network_mode = "public"`, which is
    NOT offline."""
    try:
        with (task / "task.toml").open("rb") as fh:
            cfg = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return (cfg.get("environment") or {}).get("network_mode") in ("no-network", "none")


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


def shell_assignments(code: str) -> dict[str, str]:
    """Simple `VAR=value` assignments, for resolving copy sources that hide
    behind a variable (`SOURCE="$ROOT/app"`)."""
    out: dict[str, str] = {}
    for m in re.finditer(r"(?m)^\s*(?:export\s+)?([A-Za-z_]\w*)=(.*)$", code):
        value = m.group(2).strip()
        if value[:1] in ("\"", "'"):
            # Quoted value: take everything up to the LAST matching quote, so
            # nested quotes inside $() ("$(cd "$(dirname "$0")" && pwd)")
            # survive. Anything past it is a trailing comment.
            q = value[0]
            end = value.rfind(q)
            value = value[1:end] if end > 0 else value[1:]
        else:
            value = re.split(r"[\s#]", value, maxsplit=1)[0]
        out[m.group(1)] = value
    return out


def resolve_shell_token(token: str, vars_map: dict[str, str],
                        task: Path) -> str | None:
    """Map a shell token from solve.sh to a path in the repo's solution/ dir.

    Handles the three ways an oracle refers to its own reference tree:
    $(dirname "$0"), /solution, and paths relative to the script. Returns None
    when the token cannot be resolved statically.
    """
    root = str(task / "solution")
    t = token
    for _ in range(8):
        m = re.search(r"\$\(([^()]*)\)", t)
        if m:
            inner = m.group(1).strip()
            if "dirname" in inner:
                repl = root
            else:
                cd = re.fullmatch(r"cd\s+(\S+)\s*&&\s*pwd", inner)
                if not cd:
                    return None
                repl = cd.group(1).strip("\"'")
            t = t[:m.start()] + repl + t[m.end():]
            continue
        m = re.search(r"\$(?:\{(\w+)\}|(\w+))", t)
        if not m:
            break
        name = m.group(1) or m.group(2)
        if name not in vars_map:
            return None
        t = t[:m.start()] + vars_map[name] + t[m.end():]
    if "$" in t:
        # A substitution we do not model (${VAR:-default}, arithmetic, ...)
        # survived — say so rather than resolve to a path that cannot exist.
        return None
    if t.startswith("/solution"):
        t = root + t[len("/solution"):]
    elif not t.startswith("/"):
        t = f"{root}/{t}"
    return t


def recursive_copies(code: str) -> list[tuple[str, str]]:
    """(source, destination) pairs from `cp -r/-R/-a` statements."""
    out: list[tuple[str, str]] = []
    for line in code.splitlines():
        for stmt in re.split(r"&&|\|\||;", line):
            try:
                tokens = shlex.split(stmt, posix=True)
            except ValueError:
                continue
            if not tokens or tokens[0] != "cp":
                continue
            flags = [t for t in tokens[1:] if t.startswith("-")]
            args = [t for t in tokens[1:] if not t.startswith("-")]
            if not any(re.search(r"^-[a-zA-Z]*[rRa]", f) or f == "--recursive"
                       for f in flags):
                continue
            if len(args) >= 2:
                out.extend((src, args[-1]) for src in args[:-1])
    return out


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
    offline = agent_is_offline(task)

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

    # Only a genuinely offline agent phase holds the reference to a no-install
    # rule. This project's default network_mode is "public" — a solve.sh that
    # installs from a registry is expected there and must not fail.
    for fetch in ("curl", "wget", "npm install", "npm ci", "pip install",
                  "pip3 install", "apt-get install"):
        if shape != "dimensions":
            continue
        pat = rf"(?<![\w-]){re.escape(fetch)}(?![\w-])"
        hits = [ln for ln in code.splitlines() if re.search(pat, ln)]
        if fetch.startswith("npm"):
            # `npm ci --offline` resolves from the local cache only — no
            # registry — so it honours the same constraint the agent is held
            # to. The other fetch commands have no offline flag.
            hits = [ln for ln in hits if "--offline" not in ln]
        if hits:
            if offline:
                err(f"{path}: runs {fetch!r}. The agent phase has no network and "
                    "the prompt says dependencies are already available; the "
                    "reference must not need a registry either.")
            else:
                notes.append(f"{path}: runs {fetch!r}. Network is public here, so "
                              "this resolves — but it makes the oracle depend on a "
                              "registry/host being up at grade time.")

    if re.search(r"\b(pkill|killall)\b", code):
        err(f"{path}: runs pkill/killall, which can kill the agent session and the "
            "harness alongside the app.")
    if re.search(r"NODE_ENV\s*=\s*production", code):
        err(f"{path}: sets NODE_ENV=production. npm's default --omit becomes "
            "\"dev\", silently skipping the devDependencies a frontend build needs.")

    # ---- the cross-check: does the oracle create what the verifier demands? --
    guards = sorted(set(APP_GUARD_RE.findall(read_text(task / "tests" / "test.sh"))))
    copies = recursive_copies(code)
    vars_map = shell_assignments(code)
    for required in guards:
        basename = required.rsplit("/", 1)[-1]
        # Accept either the full path or the basename: `cp x /app/server.js` and
        # `cp -R ./. /app/` with a matching source both satisfy the guard.
        if required in code or basename in code:
            continue
        # A recursive directory copy can still place the file without naming
        # it: `cp -r "$(dirname "$0")/public/." /app/public/` creates
        # /app/public/index.html. Resolve the source against solution/ and
        # look for the file on disk.
        satisfied = False
        unconfirmed: tuple[str, str] | None = None
        for src, dst in copies:
            dst = dst.rstrip("/")
            if not (required == dst or required.startswith(dst + "/")):
                continue
            resolved = resolve_shell_token(src, vars_map, task)
            if resolved is None:
                unconfirmed = unconfirmed or (src, dst)
                continue
            base = resolved.rstrip("/")
            if base.endswith("/."):
                base, landing = base[:-2], dst       # contents land in dst
            else:
                landing = f"{dst}/{Path(base).name}"  # the directory itself
            if not (required == landing or required.startswith(landing + "/")):
                continue
            rel = required[len(landing):].lstrip("/")
            if (Path(base) / rel).is_file():
                satisfied = True
                break
        if satisfied:
            continue
        if unconfirmed:
            src, dst = unconfirmed
            notes.append(f"{path}: tests/test.sh requires {required}; the oracle "
                         f"copies {src!r} to {dst!r} recursively but the file "
                         "cannot be confirmed inside it statically. Confirm the "
                         "copy ships it.")
            continue
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
    elif shape == "dimensions" and offline:
        # The agent phase is offline here, so a registry fetch cannot succeed.
        if re.search(r"\bnpm\s+(ci|install)\b(?![^\n]*--offline)", code):
            notes.append("solve.sh runs npm install. This task's agent phase runs "
                         "with no network — confirm this resolves offline, or drop it.")

    return report("check-solve-contract", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
