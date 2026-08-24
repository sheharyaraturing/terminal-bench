#!/usr/bin/env python3
"""Claim count consistency: target_claims <-> criterion count.

task.toml's [metadata].target_claims declares the intended number of atomic
claims; tests/reward.toml carries one [[criterion]] per claim. The template
documents the contract as "must equal the [[criterion]] count", so this check
enforces EXACT equality between the two.

This is the single owner of the target-vs-criterion relationship.
check-metadata-bounds enforces only the ABSOLUTE range (MIN_CLAIMS..MAX_CLAIMS)
on target_claims itself; it deliberately does not compare against the criterion
count, so the two checks complement rather than duplicate each other.

(An earlier revision of this check also counted `echo` lines in solve.sh and
asserted one echo per claim. That model was wrong: the judge grades the final
answer TEXT against each claim, not one shell echo per claim, and both shipped
tasks emit their oracle via a heredoc rather than `echo` lines. The echo
assertion has been removed.)
"""
from __future__ import annotations

from _lib import load_toml, make_err, report, task_arg


def count_criteria(reward_cfg: dict) -> int:
    criteria = reward_cfg.get("criterion")
    return len(criteria) if isinstance(criteria, list) else 0


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    err = make_err(errors)

    task_cfg = load_toml(task / "task.toml", err)
    reward_cfg = load_toml(task / "tests" / "reward.toml", err)

    meta = task_cfg.get("metadata") or {}
    target = meta.get("target_claims")
    if not isinstance(target, int):
        err(f"{task}/task.toml: [metadata].target_claims is required (int) — "
            "check-metadata-bounds also enforces this, but this check cannot "
            "proceed without it.")
        return report("check-claims-consistency", task, errors, [])

    crit_count = count_criteria(reward_cfg)

    if crit_count != target:
        err(f"{task}: [metadata].target_claims = {target} but tests/reward.toml has "
            f"{crit_count} [[criterion]] blocks. The metadata and the reward disagree "
            "— the contract is that target_claims equals the criterion count.")

    return report("check-claims-consistency", task, errors, [])


if __name__ == "__main__":
    import sys
    sys.exit(main())
