#!/usr/bin/env python3
"""The demo accounts the prompt states and the judge signs in with must match.

A drifted demo email is a silent one-sided failure: the judge types an account
a correct agent was never told to create, every signed-in criterion fails, and
the trial reads as a broken submission. The reverse — a prompt that promises an
account no dimension exercises — is a quieter waste, but still a drift worth
naming.

Skipped when the prompt contains no email-shaped token, which is the normal
case for a public or unauthenticated app.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# Author/maintainer addresses live in task.toml, not the product surface.
IGNORED_DOMAINS = ("turing.com", "anthropic.com", "example.com")


def task_arg() -> Path:
    if len(sys.argv) < 2:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <task-dir>")
    task = Path(sys.argv[1])
    if not task.is_dir():
        sys.exit(f"FATAL: {task} is not a directory")
    return task


def load_toml(path: Path, err) -> dict:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        err(f"{path}: not valid TOML - {e}")
    return {}


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


def prompts(task: Path, err) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted((task / "tests").glob("*/judge.toml")):
        cfg = load_toml(p, err)
        template = (cfg.get("judge") or {}).get("prompt_template")
        text = template if isinstance(template, str) else ""
        # Criterion descriptions can name accounts too.
        for c in cfg.get("criterion") or []:
            if isinstance(c, dict):
                text += "\n" + str(c.get("description", ""))
        out[p.parent.name] = text
    if out:
        return out
    rdir = task / "tests" / "rubric" / "browser"
    cfg = load_toml(rdir / "browser.toml", err)
    name = (cfg.get("judge") or {}).get("prompt_template") or "prompt.md"
    text = read_text(rdir / name)
    for c in cfg.get("criterion") or []:
        if isinstance(c, dict):
            text += "\n" + str(c.get("description", ""))
    if text.strip():
        out["browser"] = text
    return out


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    # An account is "discoverable" if the agent can learn about it from what it
    # was given: the prompt itself, the topic-split brief of the earlier shape,
    # or the seed data the prompt points at. fleetops states no accounts in
    # prose and hands the agent a seed file full of them — that is fine, and a
    # check that only read the prose would either miss the drift or invent one.
    sources = [task / "instruction.md"]
    instructions_dir = task / "environment" / "instructions"
    if instructions_dir.is_dir():
        sources += sorted(instructions_dir.rglob("*.md"))
    assets = task / "environment" / "assets"
    if assets.is_dir():
        sources += [p for p in sorted(assets.rglob("*"))
                    if p.is_file() and p.suffix.lower() in
                    (".json", ".csv", ".tsv", ".md", ".txt", ".yaml", ".yml")]

    stated: set[str] = set()
    for src in sources:
        stated |= {e for e in EMAIL_RE.findall(read_text(src))
                   if not e.lower().endswith(IGNORED_DOMAINS)}

    prose = {e for e in EMAIL_RE.findall(read_text(task / "instruction.md"))
             if not e.lower().endswith(IGNORED_DOMAINS)}

    if not stated:
        print(f"NOTE {task}: no demo accounts anywhere in the prompt or the seed; "
              "treating this as a public or unauthenticated app.")
        print(f"check-demo-accounts-agree: OK ({task})")
        return 0
    if not prose:
        notes.append(f"the {len(stated)} demo account(s) the judge uses come from "
                     "the seed data rather than instruction.md. That is fine — the "
                     "agent is told to load the seed — but it means the prompt "
                     "alone does not tell a reader which identities exist.")

    used_anywhere: set[str] = set()
    for dimension, text in sorted(prompts(task, err).items()):
        used = {e for e in EMAIL_RE.findall(text)
                if not e.lower().endswith(IGNORED_DOMAINS)}
        used_anywhere |= used
        # A dimension legitimately exercising only one role is normal — most
        # visual dimensions sign in as the default account and stop there. Only
        # an account NO dimension ever uses is worth mentioning, so the
        # per-dimension difference is deliberately not reported.
        for extra in sorted(used - stated):
            err(f"{task}/tests/{dimension}: the judge signs in as {extra!r}, which "
                "appears neither in the prompt nor in any seed file the agent is "
                "given. A correct submission has no such account, so every "
                "criterion using it fails for a reason the submission could not "
                "have anticipated.")

    # Only prose promises are worth reporting as unused: a seed file legitimately
    # contains many more identities than any rubric exercises.
    for unused in sorted(prose - used_anywhere):
        notes.append(f"instruction.md promises the demo account {unused!r} but no "
                     "dimension ever signs in with it — either a role the rubric "
                     "forgot to exercise, or a leftover in the prompt.")

    return report("check-demo-accounts-agree", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
