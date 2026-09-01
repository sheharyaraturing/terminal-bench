#!/usr/bin/env python3
"""The judge timeouts must nest inside the verifier's, with room to spare.

This is the single configuration mistake that turns a working task into a
silent zero. When an inner timeout is not strictly smaller than the layer above
it, the outer layer SIGKILLs the inner one mid-session: RewardKit never writes
reward-details.json, nothing collects per-criterion verdicts, and the only
reward on disk is the 0.0 placeholder — indistinguishable on the wire from a
submission that failed every criterion on the merits.

The nesting differs by shape.

  dimensions (current):
      sum of every tests/<dim>/judge.toml [judge].timeout
    < the `timeout N rewardkit` guard in tests/test.sh
    < [verifier].timeout_sec
    The sum matters because the dimensions run one after another inside a
    single rewardkit invocation — a per-dimension comparison would pass while
    the run as a whole still overruns.

  browser-rubric (earlier):
      browser.toml [judge].timeout
    < [verifier.env].REWARDKIT_TIMEOUT_SEC (when set)
    < [verifier].timeout_sec
"""
from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

# GitHub-hosted runners enforce a 6h per-job limit. The agent phase is one
# uninterrupted block, so it gets the 5h cap.
AGENT_MAX_SEC = float(os.environ.get("WEBDEV_AGENT_MAX_SEC", "18000"))
VERIFIER_SOFT_CAP_SEC = float(
    os.environ.get("WEBDEV_VERIFIER_SOFT_CAP_SEC", "36000"))
# `timeout <N> rewardkit ...` in tests/test.sh.
REWARDKIT_GUARD_RE = re.compile(r"\btimeout\s+(\d+)\s+rewardkit\b")


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


def as_seconds(value) -> float | None:
    """Coerce a TOML timeout (a number, or a string like REWARDKIT_TIMEOUT_SEC)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


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


def check_agent_and_verifier(path: Path, cfg: dict, err, notes) -> float | None:
    agent_sec = as_seconds((cfg.get("agent") or {}).get("timeout_sec"))
    verifier_sec = as_seconds((cfg.get("verifier") or {}).get("timeout_sec"))

    if agent_sec is None:
        err(f"{path}: [agent].timeout_sec is missing or not numeric.")
    elif agent_sec <= 0:
        err(f"{path}: [agent].timeout_sec = {agent_sec:g} must be positive.")
    elif agent_sec < 900:
        notes.append(f"[agent].timeout_sec = {agent_sec:g} ({agent_sec / 60:.0f} "
                     "min). Fine for a focused static page; tight for anything "
                     "with a backend to build and debug.")
    elif agent_sec > AGENT_MAX_SEC:
        err(f"{path}: [agent].timeout_sec = {agent_sec:g} exceeds the "
            f"{AGENT_MAX_SEC:g}s (5h) cap. GitHub-hosted runners enforce a 6h "
            "per-job limit and the verifier still has to run afterwards.")

    if verifier_sec is None:
        err(f"{path}: [verifier].timeout_sec is missing or not numeric.")
    elif verifier_sec > VERIFIER_SOFT_CAP_SEC:
        notes.append(f"[verifier].timeout_sec = {verifier_sec:g}s "
                     f"({verifier_sec / 3600:.1f}h) is past the "
                     f"{VERIFIER_SOFT_CAP_SEC / 3600:.0f}h soft ceiling. Confirm "
                     "the execution backend hosts jobs that long.")
    return verifier_sec


def check_dimensions(task: Path, cfg: dict, verifier_sec, err, notes) -> None:
    per_dim: dict[str, float] = {}
    for path in sorted((task / "tests").glob("*/judge.toml")):
        judge = (load_toml(path, err).get("judge") or {})
        t = as_seconds(judge.get("timeout"))
        if t is None or t <= 0:
            err(f"{path}: [judge].timeout must be a positive number, got "
                f"{judge.get('timeout')!r}. Without it RewardKit uses its own "
                "default, unrelated to the verifier budget.")
        else:
            per_dim[path.parent.name] = t

    if not per_dim:
        return
    total = sum(per_dim.values())
    notes.append("judge timeouts: "
                 + ", ".join(f"{d}={t:g}s" for d, t in sorted(per_dim.items()))
                 + f" (total {total:g}s).")

    test_sh = task / "tests" / "test.sh"
    guard = REWARDKIT_GUARD_RE.search(read_text(test_sh))
    if not guard:
        notes.append(f"{test_sh}: no `timeout <seconds> rewardkit ...` guard. "
                     "Without one a wedged judge runs until Harbor kills the whole "
                     "verifier, and the fallback that would have written a real "
                     "0.0 never executes.")
    else:
        guard_sec = float(guard.group(1))
        if total > guard_sec:
            err(f"{test_sh}: the rewardkit guard is {guard_sec:g}s but the judge "
                f"timeouts sum to {total:g}s ({', '.join(f'{d}={t:g}' for d, t in sorted(per_dim.items()))}). "
                "The dimensions run in sequence inside one rewardkit invocation, "
                "so a slow run is cut off partway and the dimensions that had not "
                "started score 0 without being judged.")
        if verifier_sec is not None and guard_sec >= verifier_sec:
            err(f"{test_sh}: the rewardkit guard ({guard_sec:g}s) must be strictly "
                f"less than [verifier].timeout_sec ({verifier_sec:g}s). Harbor "
                "kills the verifier first, so the guard never fires and the "
                "0.0-writing fallback behind it never runs.")


def check_browser_rubric(task: Path, cfg: dict, verifier_sec, err, notes) -> None:
    browser_path = task / "tests" / "rubric" / "browser" / "browser.toml"
    judge = (load_toml(browser_path, err).get("judge") or {})
    judge_sec = as_seconds(judge.get("timeout"))
    venv = (cfg.get("verifier") or {}).get("env") or {}
    rewardkit_sec = as_seconds(venv.get("REWARDKIT_TIMEOUT_SEC"))

    if judge_sec is None:
        err(f"{browser_path}: [judge].timeout is missing or not numeric.")
        return
    if judge_sec <= 0:
        err(f"{browser_path}: [judge].timeout = {judge_sec:g} must be positive.")
        return
    if verifier_sec is None:
        return

    if rewardkit_sec is not None:
        if rewardkit_sec >= verifier_sec:
            err(f"{task}/task.toml: REWARDKIT_TIMEOUT_SEC ({rewardkit_sec:g}) must "
                f"be strictly less than [verifier].timeout_sec ({verifier_sec:g}).")
        if judge_sec >= rewardkit_sec:
            err(f"{browser_path}: [judge].timeout ({judge_sec:g}) must be strictly "
                f"less than REWARDKIT_TIMEOUT_SEC ({rewardkit_sec:g}).")
    elif judge_sec >= verifier_sec:
        err(f"{browser_path}: [judge].timeout ({judge_sec:g}) must be strictly less "
            f"than [verifier].timeout_sec ({verifier_sec:g}).")

    segments = task / "tests" / "rubric" / "browser" / "segments.json"
    blocks = load_toml(browser_path, err).get("criterion") or []
    if segments.is_file() and blocks:
        worst = judge_sec * len(blocks)
        if worst > verifier_sec:
            notes.append(f"segmented rubric: {len(blocks)} criteria x {judge_sec:g}s "
                         f"= {worst:g}s worst case, above [verifier].timeout_sec "
                         f"({verifier_sec:g}s). Only reachable if every segment "
                         "times out, but then the trailing segments never run.")


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    path = task / "task.toml"
    cfg = load_toml(path, err)
    verifier_sec = check_agent_and_verifier(path, cfg, err, notes)

    shape = task_shape(task)
    if shape == "dimensions":
        check_dimensions(task, cfg, verifier_sec, err, notes)
    elif shape == "browser-rubric":
        check_browser_rubric(task, cfg, verifier_sec, err, notes)

    return report("check-timeout-hierarchy", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
