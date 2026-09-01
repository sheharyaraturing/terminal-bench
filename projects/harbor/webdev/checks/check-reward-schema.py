#!/usr/bin/env python3
"""tests/reward.toml: how the dimension scores become one number.

RewardKit walks /tests, finds each tests/<dimension>/judge.toml, and combines
them according to the [[reward]] block here. Get this file wrong and the task
still runs, still calls every judge, and still writes a reward — just not the
one the dimension weights describe.

Only the current (dimensions) shape has this file. The earlier browser-rubric
shape computes its score in tests/test.py instead, so this check is a no-op
pass there.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

# weighted_mean is the only aggregation that preserves a partial-credit
# gradient across dimensions. all_pass at the top level would collapse the
# whole task to 0 unless every dimension passed outright, which is near-certain
# for early rollouts and leaves the policy nothing to learn from.
EXPECTED_AGGREGATION = "weighted_mean"
KNOWN_AGGREGATIONS = {"weighted_mean", "all_pass", "required_pass", "mean", "min"}


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

    if task_shape(task) != "dimensions":
        print(f"NOTE {task}: not a dimensions-shaped task; tests/reward.toml does "
              "not apply (the browser-rubric shape scores in tests/test.py).")
        print(f"check-reward-schema: OK ({task})")
        return 0

    path = task / "tests" / "reward.toml"
    cfg = load_toml(path, err)
    if not cfg:
        return report("check-reward-schema", task, errors, notes)

    # A [judge] or [[criterion]] here means a half-migrated single-file rubric:
    # rewardkit reads this as the aggregate, so the dimension directories are
    # never discovered and the task grades on nothing.
    if isinstance(cfg.get("judge"), dict):
        err(f"{path}: has a [judge] table. This file is the top-level aggregate; a "
            "judge belongs in tests/<dimension>/judge.toml. With one here the "
            "dimensions are not discovered and the score is not what the weights "
            "describe.")
    if isinstance(cfg.get("criterion"), list) and cfg.get("criterion"):
        err(f"{path}: has [[criterion]] blocks. Criteria belong in a dimension's "
            "judge.toml, not in the aggregate.")

    rewards = cfg.get("reward")
    if not isinstance(rewards, list) or not rewards:
        err(f"{path}: missing [[reward]]. Without it RewardKit has no instruction "
            "for combining the dimension judges, and the task's headline score is "
            "whatever its default happens to be.")
        return report("check-reward-schema", task, errors, notes)
    if len(rewards) > 1:
        notes.append(f"{len(rewards)} [[reward]] blocks; confirm which one Harbor "
                     "reads as the headline reward.")

    for i, block in enumerate(rewards, 1):
        where = f"{path}: [[reward]] #{i}"
        if not isinstance(block, dict):
            err(f"{where}: must be a table.")
            continue
        if not str(block.get("name", "")).strip():
            err(f"{where}: name is required — it is the key the score is reported "
                "under.")
        aggregation = block.get("aggregation")
        if aggregation is None:
            err(f"{where}: aggregation is required. Leaving it implicit means the "
                "dimension weights in each judge.toml may not be what actually "
                "combines them.")
        elif aggregation not in KNOWN_AGGREGATIONS:
            err(f"{where}: aggregation = {aggregation!r} is not one of "
                f"{sorted(KNOWN_AGGREGATIONS)}.")
        elif aggregation != EXPECTED_AGGREGATION:
            notes.append(f"[[reward]] aggregation = {aggregation!r}, not "
                         f"{EXPECTED_AGGREGATION!r}. Anything that collapses to 0 "
                         "unless every dimension passes gives a training policy no "
                         "gradient — confirm this is deliberate.")

    # The dimensions themselves must exist and be non-empty, or the weighted
    # mean is taken over fewer judges than the task documents.
    dims = sorted(p.parent.name for p in (task / "tests").glob("*/judge.toml"))
    notes.append(f"{len(dims)} graded dimension(s): {', '.join(dims)}.")

    # Anything else at tests/ top level that looks like a judge but is not in a
    # dimension directory will not be discovered.
    stray = [p.name for p in (task / "tests").glob("judge.toml")]
    if stray:
        err(f"{task}/tests/judge.toml: a judge at the tests/ root is not a "
            "dimension. RewardKit discovers dimensions as tests/<name>/judge.toml; "
            "this one is either ignored or double-counted.")

    return report("check-reward-schema", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
