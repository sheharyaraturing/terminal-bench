#!/usr/bin/env python3
"""The images: reproducible, self-contained, and free of the answer key.

Two images matter. environment/Dockerfile is the agent's workbench. In the
current format tests/Dockerfile is a separate verifier image carrying the judge
toolchain; in the earlier shape there is no second image and the agent's own
carries it, because grading happens in the same container.

Whatever the shape, three properties hold:

  Pinned. An image that re-resolves on rebuild means a task which passed at
  authoring time can fail months later with no change to the task, and the
  failure looks like a bad submission.

  Self-contained. Anything fetched at trial time makes the score depend on a
  registry being reachable. This is not hypothetical when the agent phase runs
  with no network at all — then an unbaked dependency is simply a task the
  agent cannot complete.

  Clean. Neither image may carry the solution or the grading code.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

DIGEST_FROM_RE = re.compile(r"^\s*FROM\s+\S+@sha256:[0-9a-f]{64}", re.MULTILINE)
# COPY sources that would hand over the answer key or the grading code.
LEAK_SRC_RE = re.compile(r"\b(solution|solve\.sh|test\.py|test\.sh|"
                         r"browser\.toml|judge\.toml|segments\.json|rubric)\b")
# The judge drivers RewardKit can shell out to, and the package that provides each.
JUDGE_PACKAGE = {"codex": "@openai/codex", "claude-code": "@anthropic-ai/claude-code"}


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


def load_toml(path: Path, err) -> dict:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        err(f"{path}: missing")
    except tomllib.TOMLDecodeError as e:
        err(f"{path}: not valid TOML - {e}")
    return {}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def join_continuations(text: str) -> list[str]:
    """Collapse Dockerfile backslash continuations into single lines."""
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


def check_pins(path: Path, lines: list[str], code: str, err, notes) -> None:
    """Version pinning, applied to every image."""
    if not DIGEST_FROM_RE.search(code):
        notes.append(f"{path}: FROM is not digest-pinned. A floating tag "
                     "re-resolves on every rebuild, so this image can drift under "
                     "a task that has not changed and the resulting failure looks "
                     "like a bad submission. Prefer "
                     "`FROM <image>:<tag>@sha256:<digest>`.")
    if re.search(r"^\s*FROM\s+--platform=", code, re.MULTILINE):
        notes.append(f"{path}: FROM pins --platform, which forces qemu emulation "
                     "on arm64 backends. Deliberate for a genuinely single-arch "
                     "dependency; otherwise it can slow the judge into a timeout.")

    apt_lines = [ln for ln in lines
                 if re.search(r"\bapt-get\s+install|\bapt\s+install", ln)]
    if apt_lines:
        if not re.search(r"apt-get\s+update|apt\s+update", code):
            notes.append(f"{path}: apt install without apt update in the same "
                         "stage. Fine if an earlier stage or the base image "
                         "refreshed the index; otherwise pinned versions will not "
                         "resolve.")
        if "rm -rf /var/lib/apt/lists" not in code:
            notes.append(f"{path}: no `rm -rf /var/lib/apt/lists/*` after apt "
                         "install; the image carries the index for nothing.")
        if not any(re.search(r"[a-z0-9+.-]+=[0-9]", ln) for ln in apt_lines):
            notes.append(f"{path}: apt packages are not version-pinned. This image "
                         "is part of the grading runtime, so an unpinned package "
                         "changes what the verifier runs between rebuilds.")

    for ln in lines:
        if re.search(r"\bpip3?\s+install\b|\buv\s+pip\s+install\b", ln):
            specs = [m[0] or m[1] for m in re.findall(r'"([^"]+)"|\'([^\']+)\'', ln)]
            if not specs:  # unquoted form: take the bare tokens
                tail = re.split(r"\binstall\b", ln, maxsplit=1)[-1]
                specs = [t for t in tail.split()
                         if not t.startswith("-") and re.match(r"^[a-z0-9]", t, re.I)]
            for spec in specs:
                if "==" not in spec:
                    err(f"{path}: pip spec {spec!r} is unpinned. Use ==<version>; an "
                        "unpinned dependency of the verifier can change the score "
                        "with no change to the task.")
        for segment in re.split(r"&&|\|\||;", ln):
            m = re.match(r"\s*(?:RUN\s+)?npm\s+(?:install|i|add)\b(.*)", segment)
            if not m:
                continue
            for tok in m.group(1).split():
                if tok.startswith("-") or tok.startswith(">"):
                    continue
                if not re.match(r"^@?[a-z0-9._-]", tok, re.IGNORECASE):
                    continue
                pinned = tok.count("@") >= 2 if tok.startswith("@") else "@" in tok
                if not pinned:
                    err(f"{path}: npm package {tok!r} is installed without a "
                        "version. Pin it as pkg@<version>.")


def check_no_leaks(path: Path, lines: list[str], err, *, allow_tests: bool) -> None:
    for ln in lines:
        m = re.match(r"\s*(COPY|ADD)\s+(.*)", ln, re.IGNORECASE)
        if not m:
            continue
        args = [a for a in m.group(2).split() if not a.startswith("--")]
        if len(args) < 2:
            continue
        dest = args[-1]
        for src in args[:-1]:
            # The verifier image legitimately bakes /tests — that is its job.
            if allow_tests and dest.rstrip("/").endswith("/tests"):
                continue
            if LEAK_SRC_RE.search(src):
                err(f"{path}: {m.group(1).upper()} pulls in {src!r}. The solution "
                    "and the grading code must never reach the agent's container.")


def check_environment_image(task: Path, cfg: dict, shape: str, err, notes) -> None:
    path = task / "environment" / "Dockerfile"
    text = read_text(path)
    if not text.strip():
        err(f"{path}: missing or empty.")
        return
    lines = strip_comments(join_continuations(text))
    code = "\n".join(lines)

    check_pins(path, lines, code, err, notes)
    check_no_leaks(path, lines, err, allow_tests=False)

    # NODE_ENV=production makes npm's default --omit become "dev" for every
    # install in the container, silently dropping the frontend toolchain.
    if re.search(r"^\s*ENV\s+[^\n]*NODE_ENV\s*[= ]\s*production", code, re.MULTILINE):
        err(f"{path}: sets NODE_ENV=production. npm's default --omit then becomes "
            "\"dev\" for every install here — the agent's, the oracle's, and the "
            "verifier's — silently dropping devDependencies the frontend build "
            "needs.")

    if not re.search(r"^\s*WORKDIR\s+/app\s*$", code, re.MULTILINE):
        notes.append(f"{path}: no `WORKDIR /app`. /app is the app root the oracle "
                     "installs into and the verifier starts.")
    # Docker honours the LAST CMD/ENTRYPOINT, so a wait-shaped one earlier in
    # the file does not save an app-shaped one at the end.
    cmds = re.findall(r"^\s*(?:CMD|ENTRYPOINT)\s+(.*)$", code, re.MULTILINE)
    cmd = cmds[-1] if cmds else None
    if not cmd:
        err(f"{path}: no CMD. The agent container must stay alive for the agent to "
            "work in (`CMD [\"sleep\", \"infinity\"]`).")
    elif not re.search(r"sleep|tail\s+-f|wait\b|bash|sh\b", cmd):
        err(f"{path}: the effective CMD/ENTRYPOINT is {cmd.strip()!r}, which starts the "
            "application as PID 1. Harbor needs a shell in this container; an "
            "image that boots the app instead reads as a hung agent. Use a "
            "wait-shaped command (`sleep infinity`).")

    # A live fetch at build time makes the image non-reproducible and cannot
    # work in an offline build.
    if re.search(r"git\s+clone|curl[^\n|]*\|\s*(?:ba)?sh|wget[^\n|]*\|\s*(?:ba)?sh",
                 code, re.IGNORECASE):
        err(f"{path}: clones or pipes a remote script into a shell at build time. "
            "The result changes without the task changing.")

    # An offline agent phase can install nothing, so the runtime dependencies
    # the brief tells it to use must already be here.
    network = (cfg.get("environment") or {}).get("network_mode")
    if network in ("no-network", "none"):
        # Only meaningful when the reference actually declares dependencies. A
        # static page, a canvas game, or a stdlib-only server needs nothing
        # installed, and demanding an install there is a false failure.
        manifests = [p for p in (task / "solution").rglob("*")
                     if p.name in ("package.json", "requirements.txt",
                                   "pyproject.toml", "Gemfile")
                     and "node_modules" not in p.parts]
        installs = re.search(r"npm\s+install|pip3?\s+install|apt-get\s+install", code)
        if manifests and not installs:
            err(f"{path}: [environment].network_mode = {network!r} and the "
                f"reference ships {manifests[0].name}, but the image installs "
                "nothing. The agent cannot reach a registry, so the task is "
                "impossible rather than hard.")
        elif re.search(r"npm\s+install", code) and "NODE_PATH" not in code:
            notes.append(f"{path}: dependencies are installed globally but "
                         "NODE_PATH is not set; a submission doing `require()` from "
                         "/app may not resolve them.")

    if shape == "browser-rubric":
        # Shared mode: this image is also the verifier's runtime.
        check_judge_toolchain(path, code, task, err, notes)


def install_commands(code: str) -> str:
    """Only the text of actual install/download commands.

    Matching the whole file is not good enough: this Dockerfile mentions
    `@playwright/mcp` a second time inside a *fallback path string* used to
    locate the CLI. Deleting the real `npm install` line therefore left the
    package name still present, and a whole-file search reported the toolchain
    as baked when nothing installed it.
    """
    kept: list[str] = []
    for ln in code.splitlines():
        for segment in re.split(r"&&|\|\||;", ln):
            if re.search(r"\b(?:npm\s+(?:install|i|add)|pip3?\s+install|"
                         r"uv\s+pip\s+install|apt-get\s+install|"
                         r"playwright[^\n]*install|install\s+--with-deps)\b", segment):
                kept.append(segment)
    return "\n".join(kept)


def check_judge_toolchain(path: Path, code: str, task: Path, err, notes) -> None:
    """Whichever image the judge runs in must carry its whole toolchain."""
    installs = install_commands(code)
    cfg = load_toml(task / "task.toml", err)
    driver = ((cfg.get("verifier") or {}).get("env") or {}).get("REWARDKIT_JUDGE")
    package = JUDGE_PACKAGE.get(driver)

    required = [(r"@playwright/mcp", "the Playwright MCP server the judge drives "
                                     "the browser with"),
                (r"harbor-rewardkit", "the RewardKit runner"),
                (r"install\b[^\n]*chromium", "a Chromium build for the headless "
                                             "browser")]
    if package:
        required.append((re.escape(package), f"the {driver!r} judge driver"))
    elif driver:
        notes.append(f"REWARDKIT_JUDGE = {driver!r} is not one of "
                     f"{sorted(JUDGE_PACKAGE)}; cannot verify its driver is baked.")

    for pattern, why in required:
        if not re.search(pattern, installs):
            err(f"{path}: does not install {why}. Installing it at trial time makes "
                "grading depend on a registry being reachable.")

    if "PLAYWRIGHT_BROWSERS_PATH" not in code:
        notes.append(f"{path}: PLAYWRIGHT_BROWSERS_PATH is not set. Chromium then "
                     "lands in the build user's home; that works when the judge "
                     "runs as the same user, and breaks when it does not.")

    # codex reads its provider config from a file, not the environment.
    if driver == "codex" and ".codex/config.toml" not in code:
        notes.append(f"{path}: the judge driver is codex but no "
                     "/root/.codex/config.toml is written here. codex normally "
                     "resolves its provider from that file — confirm it is "
                     "configured somewhere, or the key is set and never used.")


def check_verifier_image(task: Path, err, notes) -> None:
    path = task / "tests" / "Dockerfile"
    text = read_text(path)
    if not text.strip():
        err(f"{path}: missing or empty (separate verifier mode needs it).")
        return
    lines = strip_comments(join_continuations(text))
    code = "\n".join(lines)

    check_pins(path, lines, code, err, notes)
    check_no_leaks(path, lines, err, allow_tests=True)
    check_judge_toolchain(path, code, task, err, notes)

    # Separate mode sets skip_tests_upload, so the image must own /tests.
    if not re.search(r"chmod[^\n]*\+x[^\n]*test\.sh|chmod\s+[0-7]*7[0-7]{2}"
                     r"[^\n]*test\.sh", code):
        notes.append(f"{path}: never chmods tests/test.sh executable. Harbor "
                     "usually invokes it through bash, but an image that bakes it "
                     "non-executable is one `./test.sh` away from a silent failure.")

    # Whatever the rubric names as its MCP command has to exist in this image.
    commands: set[str] = set()
    for jt in sorted((task / "tests").glob("*/judge.toml")):
        for s in (load_toml(jt, err).get("judge") or {}).get("mcp_servers") or []:
            if isinstance(s, dict) and s.get("command"):
                commands.add(str(s["command"]))
    # The command is a binary name; the Dockerfile names a package. They differ
    # in punctuation only ("playwright-mcp" vs "@playwright/mcp"), so compare
    # with separators stripped rather than as literal substrings.
    def squash(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower())

    squashed_code = squash(install_commands(code))
    for command in sorted(commands):
        base = command.split("/")[-1]
        if squash(base) not in squashed_code:
            err(f"{path}: a judge declares the MCP command {command!r}, but nothing "
                "in this image installs or provides it. The judge starts with no "
                "browser and scores every criterion from the prompt alone.")

    if not re.search(r"^\s*(COPY|ADD)\b.*\s/tests(/|\s|$)", code,
                     re.MULTILINE | re.IGNORECASE):
        err(f"{path}: no COPY/ADD into /tests. Separate verifier mode skips the "
            "tests/ upload, so the image has to bake the grading code itself.")


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    cfg = load_toml(task / "task.toml", err)
    shape = task_shape(task)

    check_environment_image(task, cfg, shape, err, notes)
    if shape == "dimensions":
        check_verifier_image(task, err, notes)

    return report("check-dockerfiles", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
