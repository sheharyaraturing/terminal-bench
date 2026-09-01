#!/usr/bin/env python3
"""The verifier's allowlist must cover the host its wired key actually calls.

check-task-toml.py only requires the allowlist to be non-empty. This one closes
the loop: if the verifier holds an OPENROUTER_API_KEY but the allowlist names
some other host, the judge's very first model call is refused at the network
layer. Every dimension scores 0 and the log reads as an auth or infra failure,
which is the hardest kind of task bug to attribute.

Hosts beyond the judge provider are a NOTE — each one is another place a
prompt-injected judge could send data.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

# env key name -> the host that key authenticates against.
KEY_HOSTS = {
    "OPENROUTER_API_KEY": "openrouter.ai",
    "OPENAI_API_KEY": "api.openai.com",
    "ANTHROPIC_API_KEY": "api.anthropic.com",
    "ANTHROPIC_AUTH_TOKEN": "openrouter.ai",
    "GEMINI_API_KEY": "generativelanguage.googleapis.com",
    "GOOGLE_API_KEY": "generativelanguage.googleapis.com",
}


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
        err(f"{path}: missing")
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


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    path = task / "task.toml"
    cfg = load_toml(path, err)
    verifier = cfg.get("verifier") or {}
    venv = verifier.get("env") or {}
    hosts = (verifier.get("environment") or {}).get("allowed_hosts")

    if not isinstance(hosts, list) or not hosts:
        print(f"NOTE {task}: the verifier declares no allowed_hosts (no allowlist "
              "in force); check-task-toml.py owns whether it should.")
        print(f"check-allowlist-matches-provider: OK ({task})")
        return 0

    hosts_l = [str(h).lower() for h in hosts]
    needed: set[str] = set()
    for key, host in KEY_HOSTS.items():
        value = venv.get(key)
        # An empty value is a deliberate unset (both shapes do this to stop a
        # client picking up a stray key), not a provider in use.
        if isinstance(value, str) and value.strip():
            needed.add(host)

    for host in sorted(needed):
        if not any(host in h or h in host for h in hosts_l):
            err(f"{path}: [verifier.env] wires a key for {host!r} but "
                f"[verifier.environment].allowed_hosts = {hosts} does not include "
                "it. The judge's first model call is refused at the network layer, "
                "every dimension scores 0, and the failure reads as infrastructure "
                "rather than as a task bug.")

    extra = [h for h in hosts_l if not any(n in h or h in n for n in needed)]
    if extra:
        notes.append(f"allowed_hosts includes {extra} beyond the judge provider. "
                     "Each additional host is somewhere a prompt-injected judge "
                     "could send what it read from the submission.")

    return report("check-allowlist-matches-provider", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
