#!/usr/bin/env python3
"""tests/reward.toml: the rewardkit judge contract.

The mechanical shape only - whether the claims are *correct* is the rubric's
job, not a deterministic check's.
"""
from __future__ import annotations

from _lib import (JUDGE_MODEL, MAX_CLAIMS, MIN_CLAIMS, load_toml, make_err,
                  report, task_arg)


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    reward_path = task / "tests" / "reward.toml"
    reward_cfg = load_toml(reward_path, err)
    judge = reward_cfg.get("judge")
    criteria = reward_cfg.get("criterion")

    if not isinstance(judge, dict):
        err(f"{reward_path}: missing [judge]. rewardkit only treats a .toml as a judge "
            "reward when it has BOTH [judge] and [[criterion]]; without [judge] this file "
            "is silently ignored and the task has no reward at all.")
        judge = {}
    if not isinstance(criteria, list) or not criteria:
        err(f"{reward_path}: missing [[criterion]] blocks.")
        criteria = []

    # The key is `judge`, NOT `model`. rewardkit reads judge_config.get("judge")
    # and only passes `model` through for an AGENT judge. A [judge].model line on
    # an LLM judge is dead config: it grades with the default model and nothing
    # warns you.
    declared = judge.get("judge")
    if declared is None:
        if "model" in judge:
            err(f"{reward_path}: [judge].model is IGNORED for an LLM judge - rewardkit reads "
                f"[judge].judge. Rename the key: judge = \"{JUDGE_MODEL}\".")
        else:
            err(f"{reward_path}: [judge].judge is unset, so rewardkit falls back to its "
                f"default judge model. Set judge = \"{JUDGE_MODEL}\".")
    elif not (isinstance(declared, str) and declared.startswith("openrouter/")):
        # Only the prefix is load-bearing: it is what makes litellm read
        # OPENROUTER_API_KEY. The specific model is the task author's choice.
        err(f"{reward_path}: [judge].judge is {declared!r}, expected an 'openrouter/'-prefixed "
            "model id. Without the prefix litellm does not read OPENROUTER_API_KEY and the "
            "judge call fails auth.")
    elif declared != JUDGE_MODEL:
        notes.append(f"[judge].judge is {declared!r}, not the suite default {JUDGE_MODEL!r}. "
                     "Allowed - only the openrouter/ prefix is load-bearing - but confirm the "
                     "choice is deliberate.")

    if judge.get("mode") != "individual":
        err(f"{reward_path}: [judge].mode must be \"individual\". The benchmark scores each "
            "claim independently; \"batched\" (rewardkit's default) grades them as one blob "
            "and destroys the partial-credit signal.")

    # With no files the judge is handed the system prompt ALONE and grades with
    # zero evidence - every claim scores ~0 and the cascade becomes noise.
    files = judge.get("files")
    if not isinstance(files, list) or not files:
        err(f"{reward_path}: [judge].files is required and must be non-empty. rewardkit sends "
            "the judge ONLY the listed file contents; with no files it grades on the system "
            "prompt alone and every claim scores ~0.")
        files = []
    for f in files:
        if not isinstance(f, str) or not f.startswith("/logs/"):
            err(f"{reward_path}: [judge].files entry {f!r} must be an absolute path under "
                "/logs/ - that is what is mounted into the verifier.")
        if isinstance(f, str) and f.endswith("trajectory.json"):
            err(f"{reward_path}: [judge].files must not include a trajectory. rewardkit's "
                "_MAX_FILE_SIZE is 1 MB and a long-horizon trajectory is far larger; the "
                "judge receives '[skipped: file too large]' and grades on nothing.")

    # The oracle bridge in tests/test.sh writes the answer to final_answer.txt.
    # If the judge is not pointed at that file it is handed no evidence and the
    # `-a oracle` gate can never pass.
    if files and "/logs/agent/final_answer.txt" not in files:
        err(f"{reward_path}: [judge].files does not include /logs/agent/final_answer.txt. "
            "tests/test.sh bridges the agent/oracle output there; without it the judge "
            "grades on no evidence and the oracle gate can never pass.")
    extra = [f for f in files if f != "/logs/agent/final_answer.txt"]
    if extra:
        notes.append(f"[judge].files includes extra path(s) {extra}. Remember rewardkit's "
                     "_MAX_FILE_SIZE is 1 MB - an oversized file is skipped and the judge "
                     "grades on less evidence.")

    if not (MIN_CLAIMS <= len(criteria) <= MAX_CLAIMS):
        err(f"{reward_path}: {len(criteria)} claims, expected {MIN_CLAIMS}-{MAX_CLAIMS}. "
            "Too few and the reward is coarse; too many and each claim stops being atomic.")

    for i, c in enumerate(criteria, 1):
        where = f"{reward_path}: [[criterion]] #{i}"
        if not isinstance(c, dict) or not str(c.get("description", "")).strip():
            err(f"{where}: missing a non-empty description")
            continue
        # type defaults to "binary" and points defaults to 5 in rewardkit. Both
        # must be explicit: likert/3 reproduces MCP-Atlas's three outcomes after
        # rewardkit's (raw - 1) / (points - 1) normalisation.
        if c.get("type") != "likert":
            err(f"{where}: type = {c.get('type')!r}, expected \"likert\" "
                "(omitting it silently means \"binary\", which throws away partial credit)")
        if c.get("points") != 3:
            err(f"{where}: points = {c.get('points')!r}, expected 3 "
                "(omitting it silently means 5, which is not the benchmark's scale)")
        w = c.get("weight", 1.0)
        if not isinstance(w, (int, float)) or w <= 0:
            err(f"{where}: weight must be a positive number, got {w!r}")

    aggregation = (reward_cfg.get("scoring") or {}).get("aggregation", "weighted_mean")
    if aggregation != "weighted_mean":
        err(f"{reward_path}: [scoring].aggregation = {aggregation!r}, expected \"weighted_mean\". "
            "all_pass/required_pass collapse to 0.0 unless every claim lands, which is "
            "near-certain for early rollouts - the policy gets no gradient to learn from.")

    return report("check-reward-schema", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
