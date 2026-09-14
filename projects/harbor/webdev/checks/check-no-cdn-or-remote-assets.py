#!/usr/bin/env python3
"""Nothing served to the browser may be fetched off-origin.

Grade-time has no CDN network, and the judges' global gate requires
same-origin requests. A reference that pulls a font from fonts.googleapis, or a
prompt that implies a CDN script tag, works perfectly on the author's laptop
and then renders unstyled — or fails the same-origin gate outright — inside the
verifier. The failure looks like a broken submission.

Only files that reach a browser are scanned. Judge-provider URLs under tests/
and allowlist comments in task.toml are the verifier's own business.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

CDN_HOST = re.compile(
    r"https?://(?:[\w.-]*\.)?(?:cdn[\w.-]*|unpkg\.com|jsdelivr\.net|cdnjs\."
    r"cloudflare\.com|fonts\.googleapis\.com|fonts\.gstatic\.com|"
    r"ajax\.googleapis\.com|code\.jquery\.com|stackpath\.bootstrapcdn\.com)"
    r"[^\s\"'()<>]*", re.IGNORECASE)
# Any off-origin resource pulled by served markup.
REMOTE_TAG = re.compile(
    r"<(?:script|link|img|source|iframe|video|audio)\b[^>]*?"
    r"(?:src|href)\s*=\s*[\"'](https?://[^\"']+)[\"']", re.IGNORECASE)
LOCAL = re.compile(r"^https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0)")
SERVED_SUFFIXES = {".html", ".htm", ".css", ".js", ".mjs", ".jsx", ".ts", ".tsx", ".svg"}


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


def grade_time_is_offline(task: Path) -> bool:
    """True when the browser doing the grading cannot reach the open internet."""
    try:
        with (task / "task.toml").open("rb") as fh:
            cfg = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    verifier = cfg.get("verifier") or {}
    vnet = (verifier.get("environment") or {}).get("network_mode")
    if vnet in ("allowlist", "no-network", "none"):
        return True
    # Shared-mode tasks grade in the agent's container.
    if verifier.get("environment_mode") != "separate":
        return (cfg.get("environment") or {}).get("network_mode") in (
            "no-network", "none")
    return False


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    offline = grade_time_is_offline(task)
    targets = [task / "instruction.md"]
    for root in ("solution", "environment/assets"):
        base = task / root
        if base.is_dir():
            targets += [p for p in sorted(base.rglob("*"))
                        if p.is_file() and p.suffix.lower() in SERVED_SUFFIXES
                        and "node_modules" not in p.parts]

    for path in targets:
        text = read_text(path)
        if not text:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            # A line telling the agent NOT to use a CDN is the right behaviour.
            if re.search(r"\b(no|not|never|avoid|without|don'?t)\b[^.]{0,40}\bcdn\b",
                         line, re.IGNORECASE):
                continue
            for m in CDN_HOST.finditer(line):
                message = f"{path}:{i}: fetches {m.group(0)!r} from a CDN."
                if offline:
                    err(message + " Grade-time has no route to it, so the resource "
                        "never loads inside the verifier and a same-origin gate may "
                        "zero the dimension outright.")
                else:
                    notes.append(message + " Grade-time still has network here, so "
                                 "it resolves — but it makes every run depend on a "
                                 "third-party host staying up, and it breaks the "
                                 "moment this task moves to an allowlist.")
            for m in REMOTE_TAG.finditer(line):
                url = m.group(1)
                if LOCAL.match(url) or CDN_HOST.search(url):
                    continue  # localhost is fine; CDN already reported above
                message = (f"{path}:{i}: served markup loads the off-origin "
                           f"resource {url!r}.")
                if offline:
                    err(message + " It will not resolve in the verifier, and the "
                        "same-origin gate may zero the dimension outright.")
                else:
                    notes.append(message + " It resolves today, but it is an "
                                 "external dependency inside a graded run.")

    return report("check-no-cdn-or-remote-assets", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
