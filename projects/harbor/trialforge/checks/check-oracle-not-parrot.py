#!/usr/bin/env python3
"""The oracle must be a real answer, not a restatement of the claim strings.

NOTES.md / CONTRIBUTING.md: a solve.sh that parrots the criterion descriptions
passes the judge while proving nothing about whether the task is solvable from
the environment. The honest test: would this text convince the persona?
"""
from __future__ import annotations

import re

from _lib import load_toml, make_err, read_text, report, task_arg

# If the oracle shares this fraction of a claim's content words, it is parroting.
OVERLAP_THRESHOLD = 0.6
MIN_CLAIM_WORDS = 4
WORD = re.compile(r"[a-z0-9]+")
STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "that", "as", "by",
    "for", "on", "with", "at", "from", "be", "are", "was", "were", "it", "its",
    "this", "these", "those", "not", "than", "then", "so", "such", "into",
}


def words(text: str) -> set[str]:
    return {w for w in WORD.findall(text.lower()) if w not in STOP and len(w) > 2}


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    err = make_err(errors)

    solve = task / "solution" / "solve.sh"
    solve_text = read_text(solve)
    if not solve_text.strip():
        err(f"{solve}: empty. The oracle is the acceptance gate - it must contain "
            "a real answer that satisfies every claim.")
        return report("check-oracle-not-parrot", task, errors, [])
    if "CHANGE-ME" in solve_text:
        # check-no-placeholders reports this too; skip the overlap math.
        return report("check-oracle-not-parrot", task, errors,
                      ["solve.sh is still the TEMPLATE placeholder"])

    reward_cfg = load_toml(task / "tests" / "reward.toml", err)
    criteria = reward_cfg.get("criterion") or []
    solve_words = words(solve_text)
    if not solve_words:
        return report("check-oracle-not-parrot", task, errors, [])

    for i, c in enumerate(criteria, 1):
        if not isinstance(c, dict):
            continue
        desc = str(c.get("description") or "")
        cw = words(desc)
        if len(cw) < MIN_CLAIM_WORDS:
            continue
        overlap = len(cw & solve_words) / len(cw)
        if overlap >= OVERLAP_THRESHOLD:
            err(f"{solve}: shares {overlap:.0%} of [[criterion]] #{i}'s content words. "
                "An oracle that parrots the claim text passes the judge while proving "
                "nothing about whether the task is solvable from the environment. Write "
                "the answer a real analyst would give.")

    return report("check-oracle-not-parrot", task, errors, [])


if __name__ == "__main__":
    raise SystemExit(main())
