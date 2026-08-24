#!/usr/bin/env python3
"""tests/reward.toml: the toolathon rewardkit aggregate contract.

Toolathon grades via per-dimension tests/<dir>/check.py functions and aggregates
them with two [[reward]] blocks (a_reward + reward), both weighted_mean. This is
identical across all 16 tasks. The trialforge [judge] + [[criterion]] contract is
a DIFFERENT format - its presence here means a task was half-migrated.
"""
from __future__ import annotations

import sys

from _lib import load_toml, make_err, report, task_arg

EXPECTED_NAMES = {"a_reward", "reward"}


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    reward_path = task / "tests" / "reward.toml"
    reward_cfg = load_toml(reward_path, err)
    if not reward_cfg:
        return report("check-reward-schema-toolathon", task, errors, notes)

    # Reject the trialforge (LLM-judge) contract outright.
    if "judge" in reward_cfg or "criterion" in reward_cfg:
        err(f"{reward_path}: contains [judge] or [[criterion]] - that is the trialforge "
            "LLM-judge format, not toolathon. Toolathon aggregates per-dimension "
            "tests/<dir>/check.py via [[reward]] blocks only.")

    rewards = reward_cfg.get("reward")
    if not isinstance(rewards, list) or not rewards:
        err(f"{reward_path}: missing [[reward]] blocks. Toolathon aggregates dimensions "
            "via [[reward]] entries (a_reward + reward).")
        rewards = []

    names = [r.get("name") for r in rewards if isinstance(r, dict)]
    for i, r in enumerate(rewards, 1):
        if not isinstance(r, dict):
            err(f"{reward_path}: [[reward]] #{i} is not a table")
            continue
        if not str(r.get("name", "")).strip():
            err(f"{reward_path}: [[reward]] #{i} missing a non-empty name")
        if r.get("aggregation") != "weighted_mean":
            err(f"{reward_path}: [[reward]] #{i} ({r.get('name')!r}) aggregation = "
                f"{r.get('aggregation')!r}, expected \"weighted_mean\". all_pass collapses "
                "to 0.0 unless every dimension lands; weighted_mean preserves partial credit.")

    # The canonical pair must both be present.
    missing = sorted(EXPECTED_NAMES - set(names))
    if missing:
        err(f"{reward_path}: missing [[reward]] block(s) named {missing}. Harbor reads the "
            "aggregate under the canonical names a_reward + reward.")

    return report("check-reward-schema-toolathon", task, errors, notes)


if __name__ == "__main__":
    sys.exit(main())
