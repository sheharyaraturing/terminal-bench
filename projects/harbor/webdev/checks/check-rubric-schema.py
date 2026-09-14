#!/usr/bin/env python3
"""The judge rubric's mechanical contract, for whichever shape the task uses.

Current format: one tests/<dimension>/judge.toml per graded dimension, each a
self-contained judge with an inline prompt_template (or a prompt file beside
judge.toml) and its own criteria. Earlier format: a single
tests/rubric/browser/browser.toml.

The judge's identity — driver, model and reasoning effort — is NOT part of a
judge.toml any more. It is declared once in task.toml's [verifier.env]
(REWARDKIT_JUDGE / REWARDKIT_MODEL / REWARDKIT_REASONING_EFFORT), which is what
rewardkit actually reads, so a judge.toml now carries only its own grading
shape: mode, timeout, isolated, temperature, weight, prompt_template, its
[[judge.mcp_servers]] and its [[criterion]] blocks.

Whether a criterion actually discriminates a real implementation from a shell
is the rubric reviewer's job. What is checked here is every field whose absence
changes the score with no warning — a rubric that parses fine and grades the
wrong thing, or grades nothing at all.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

# A dimension is free to carry one criterion (a gate) or many.
MIN_CRITERIA_PER_DIMENSION = 1
MIN_CRITERIA_TOTAL = 8
# Chromium in a container cannot start without --no-sandbox, and the judge then
# fails every criterion for want of a browser.
REQUIRED_PLAYWRIGHT_ARGS = ("--headless", "--no-sandbox")
# RewardKit substitutes the criteria list here. Without it the judge is handed a
# prompt describing the app and NO criteria, and scores whatever it feels like.
CRITERIA_PLACEHOLDER = "{criteria}"
KNOWN_AGGREGATIONS = {"weighted_mean", "all_pass", "required_pass", "mean", "min"}
# The judge driver, its model and its reasoning effort are declared ONCE, in
# task.toml's [verifier.env]; rewardkit reads them from the verifier
# environment. Only the presence of each key is contractual — the value is the
# task's own choice (a different driver, a different model id, a different
# effort) and is never asserted here.
CENTRAL_JUDGE_KEYS = {
    "judge": "REWARDKIT_JUDGE",
    "model": "REWARDKIT_MODEL",
    "reasoning_effort": "REWARDKIT_REASONING_EFFORT",
}
# What a judge.toml's [judge] table is expected to carry now that the identity
# keys have moved to task.toml. mcp_servers arrives as [[judge.mcp_servers]].
# Anything else is surfaced as a note, not a failure: rewardkit may grow a key
# this list has not caught up with.
KNOWN_JUDGE_KEYS = {
    "mode", "timeout", "isolated", "temperature", "weight", "prompt_template",
    "mcp_servers",
}


def task_arg() -> Path:
    if len(sys.argv) < 2:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <task-dir>")
    task = Path(sys.argv[1])
    if not task.is_dir():
        sys.exit(f"FATAL: {task} is not a directory")
    return task


def task_shape(task: Path) -> str:
    if sorted((task / "tests").glob("*/judge*.toml")):
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


def criteria(cfg: dict) -> list[dict]:
    blocks = cfg.get("criterion")
    if not isinstance(blocks, list):
        return []
    return [c for c in blocks if isinstance(c, dict)]


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


def verifier_env(task: Path, err) -> dict:
    """task.toml is the single source for the judge driver, model and effort.

    Every dimension is graded by the same judge because they all inherit these
    three from the verifier environment. Leave one out and rewardkit falls back
    to whatever its own default happens to be on the day — the task did not
    choose its grader, and a re-run after a rewardkit bump silently grades with
    a different model. Only presence is checked: which driver, which model id
    and which effort are the task's call.
    """
    cfg = load_toml(task / "task.toml", err)
    venv = (cfg.get("verifier") or {}).get("env") or {}
    for key, env_key in sorted(CENTRAL_JUDGE_KEYS.items()):
        value = venv.get(env_key)
        if not isinstance(value, str) or not value.strip():
            err(f"{task / 'task.toml'}: [verifier.env].{env_key} is missing or "
                f"empty, and it is now the ONLY place the judge {key!r} is "
                "declared (judge.toml no longer carries it). Without it "
                "rewardkit grades with its own default and the task never "
                "chose its grader.")
    return venv


def check_central_judge_keys(path: Path, judge: dict, venv: dict, err) -> None:
    """A judge.toml must not re-declare the identity task.toml owns.

    The judge driver, model and reasoning effort are declared in exactly one
    place — task.toml's [verifier.env] — so a copy here is a defect whatever
    its value. One that disagrees is the loud version: this dimension reads as
    if it is graded by a different model than its siblings, and the reward
    looks like a blend of two graders nobody intended to compare. One that
    agrees is the quiet version: it grades correctly today and silently stops
    agreeing the first time the model is bumped in task.toml and not here.
    """
    for key, env_key in CENTRAL_JUDGE_KEYS.items():
        if key not in judge:
            continue
        want, got = venv.get(env_key), judge.get(key)
        if isinstance(want, str) and want.strip() and got != want:
            err(f"{path}: [judge].{key} = {got!r} contradicts task.toml's "
                f"[verifier.env].{env_key} = {want!r}. The judge identity is "
                f"declared ONLY in task.toml — delete [judge].{key}.")
        else:
            err(f"{path}: [judge].{key} = {got!r} re-declares what task.toml's "
                f"[verifier.env].{env_key} owns. The judge identity is declared "
                f"ONLY in task.toml; a second copy here agrees today and drifts "
                f"the first time the model is bumped in one place and not the "
                f"other — delete [judge].{key}.")


def check_judge_key_set(path: Path, judge: dict, notes: list[str]) -> None:
    extra = sorted(set(judge) - KNOWN_JUDGE_KEYS - set(CENTRAL_JUDGE_KEYS))
    if extra:
        notes.append(f"{path}: [judge] carries unrecognised key(s) "
                     f"{', '.join(extra)}. A judge.toml is expected to carry "
                     f"only {', '.join(sorted(KNOWN_JUDGE_KEYS))} — confirm "
                     "rewardkit consumes these, or they are text that grades "
                     "nothing.")


def check_prompt_template(path: Path, judge: dict, base: Path, err) -> None:
    """prompt_template is either the prompt itself or the name of a file.

    Which of the two is the task's choice; both are accepted. What is not
    optional is the {criteria} placeholder, wherever the prompt text ends up:
    rewardkit substitutes the criteria list there, and without it the judge is
    handed a prompt describing the app and NO criteria, and scores on nothing.
    """
    template = judge.get("prompt_template")
    if not isinstance(template, str) or not template.strip():
        err(f"{path}: [judge].prompt_template is required and must be the "
            "inline prompt for this dimension, or the name of a prompt file "
            "beside it.")
        return
    # A single-line value with no braces is a filename, not a prompt.
    if "\n" not in template and "{" not in template:
        candidate = base / template.strip()
        if not candidate.is_file():
            err(f"{path}: [judge].prompt_template = {template!r} does not "
                f"exist at {candidate}.")
        elif CRITERIA_PLACEHOLDER not in candidate.read_text(encoding="utf-8",
                                                             errors="replace"):
            err(f"{candidate}: prompt file has no {CRITERIA_PLACEHOLDER} "
                "placeholder. RewardKit substitutes the criteria there; "
                "without it the judge is handed a prompt with NO criteria "
                "and scores on nothing.")
    elif CRITERIA_PLACEHOLDER not in template:
        err(f"{path}: [judge].prompt_template has no {CRITERIA_PLACEHOLDER} "
            "placeholder. RewardKit substitutes the criteria there; without it "
            "the judge is handed a prompt with NO criteria and scores on "
            "nothing.")


def check_playwright(path: Path, cfg: dict, err) -> None:
    servers = (cfg.get("judge") or {}).get("mcp_servers")
    if not isinstance(servers, list) or not servers:
        err(f"{path}: no [[judge.mcp_servers]]. The judge has no browser and "
            "cannot exercise a single criterion.")
        return
    playwright = [s for s in servers if isinstance(s, dict)
                  and (s.get("name") == "playwright"
                       or "playwright" in str(s.get("command", "")))]
    if not playwright:
        err(f"{path}: no Playwright MCP server declared in [[judge.mcp_servers]].")
    for s in playwright:
        if s.get("transport") not in (None, "stdio"):
            err(f"{path}: Playwright MCP transport = {s.get('transport')!r}; the "
                "image installs @playwright/mcp as a local binary (stdio).")
        args = s.get("args") if isinstance(s.get("args"), list) else []
        for required in REQUIRED_PLAYWRIGHT_ARGS:
            if required not in args:
                err(f"{path}: Playwright MCP args are missing {required!r}. "
                    "Chromium cannot start in the container without it and the "
                    "judge fails every criterion for want of a browser.")


def check_criteria(path: Path, cfg: dict, err, notes: list[str],
                   minimum: int) -> list[str]:
    blocks = criteria(cfg)
    if not blocks:
        err(f"{path}: no [[criterion]] blocks — this rubric grades nothing.")
    elif len(blocks) < minimum:
        notes.append(f"{path}: {len(blocks)} criteria. Thin, but a focused "
                     "dimension legitimately carries few.")
    seen: dict[str, int] = {}
    for i, c in enumerate(blocks, 1):
        where = f"{path}: [[criterion]] #{i}"
        cid = c.get("id")
        if not isinstance(cid, str) or not cid.strip():
            err(f"{where}: missing a non-empty id. Per-criterion results are "
                "keyed by id.")
        else:
            if cid in seen:
                err(f"{where}: duplicate id {cid!r} (already used by #{seen[cid]}). "
                    "A duplicate silently overwrites the earlier verdict.")
            seen[cid] = i
            if c.get("name") not in (None, cid):
                notes.append(f"{where}: name = {c.get('name')!r} but id = {cid!r}. "
                             "Harmless, but the breakdown reports one and lookups "
                             "key off the other.")
        # binary for a pass/fail behaviour; likert for a genuinely graded
        # quality (visual craft, production readiness) where a hard threshold
        # would be arbitrary. Anything else is a typo that RewardKit silently
        # treats as binary.
        ctype = c.get("type")
        if ctype not in ("binary", "likert"):
            err(f"{where}: type = {ctype!r}, expected \"binary\" or \"likert\". "
                "RewardKit defaults an unrecognised type to binary, so a typo "
                "silently collapses a graded scale to pass/fail.")
        elif ctype == "likert" and not isinstance(c.get("points"), int):
            err(f"{where}: type = \"likert\" without an explicit integer points. "
                "RewardKit defaults to 5 — state the scale rather than inheriting "
                "one, since the normalisation is (raw - 1) / (points - 1).")
        elif ctype == "binary" and "points" in c:
            notes.append(f"{where}: type = \"binary\" with points = "
                         f"{c.get('points')!r}; points applies only to likert and "
                         "is ignored here.")
        w = c.get("weight")
        if not isinstance(w, (int, float)) or isinstance(w, bool) or w <= 0:
            err(f"{where}: weight must be a positive number, got {w!r}.")
        description = str(c.get("description", "")).strip()
        if not description:
            err(f"{where}: missing a non-empty description — the description IS "
                "the instruction the judge follows.")
        elif len(description) < 80:
            notes.append(f"{path.parent.name}/{cid or i}: description is "
                         f"{len(description)} chars. A browser criterion has to "
                         "name the action and the observable outcome.")
    return list(seen)


def check_dimensions(task: Path, err, notes: list[str]) -> None:
    venv = verifier_env(task, err)

    # A dimension directory with a prompt but no judge config is a dimension
    # that silently contributes nothing to the weighted mean. What makes a
    # directory look like a dimension is the prompt.md; pure-data support
    # directories (fixtures/, deck/, docs/, __judge__/, assets/) carry none and
    # are not dimensions. A judge*.toml glob satisfies presence — some
    # verifiers discover their judges that way — but anything other than
    # exactly judge.toml is worth a confirmation, because rewardkit's own
    # discovery looks for judge.toml.
    for d in sorted((task / "tests").iterdir()):
        if not d.is_dir() or d.name in ("rubric", "assets"):
            continue
        judges_here = sorted(d.glob("judge*.toml"))
        if judges_here:
            if not (d / "judge.toml").is_file():
                notes.append(f"{d}: dimension uses non-standard judge filename(s) "
                             f"{', '.join(p.name for p in judges_here)}. rewardkit's "
                             "own discovery looks for judge.toml — confirm the "
                             "verifier globs judge*.toml itself.")
            continue
        if (d / "prompt.md").is_file():
            err(f"{d}: dimension directory has a prompt but no judge.toml, so "
                "rewardkit discovers nothing here and the dimension contributes "
                "nothing.")

    judges = sorted((task / "tests").glob("*/judge.toml"))
    all_ids: dict[str, str] = {}
    total_criteria = 0
    weights: dict[str, float] = {}

    for path in judges:
        dim = path.parent.name
        cfg = load_toml(path, err)
        judge = cfg.get("judge")
        if not isinstance(judge, dict):
            err(f"{path}: missing [judge]. RewardKit only treats a .toml as a judge "
                "reward when it has BOTH [judge] and [[criterion]]; without it the "
                "dimension is silently ignored and contributes nothing.")
            continue

        # One driver and one model across every dimension, inherited from
        # task.toml rather than repeated here.
        check_central_judge_keys(path, judge, venv, err)
        check_judge_key_set(path, judge, notes)

        # mode and isolated are required KEYS: absent, rewardkit picks its own
        # default and the dimension never chose how it is graded. Which value a
        # task picks is its own call — an unexpected one is a note, not a
        # failure.
        mode = judge.get("mode")
        if not isinstance(mode, str) or not mode.strip():
            err(f"{path}: [judge].mode is required and must be a non-empty "
                f"string, got {mode!r}. Without it rewardkit decides whether "
                "this dimension's criteria share one browser session or get a "
                "run each, and the task never chose.")
        elif mode != "batched":
            notes.append(f"{path}: [judge].mode = {mode!r}, not "
                         "\"batched\". Splitting a dimension is allowed; just "
                         "confirm no criterion depends on what an earlier one "
                         "wrote.")
        isolated = judge.get("isolated")
        if not isinstance(isolated, bool):
            err(f"{path}: [judge].isolated is required and must be a boolean, "
                f"got {isolated!r}. Without it rewardkit decides whether each "
                "criterion gets a fresh app, which silently breaks any "
                "criterion that inspects an earlier write.")
        elif isolated is not False:
            notes.append(f"{path}: [judge].isolated = {isolated!r}. "
                         "An isolated judge gets a fresh app per criterion, which "
                         "breaks any criterion that inspects an earlier write.")

        # A reward signal that moves when nothing changed is unusable for
        # training; temperature 0 is what makes a re-run comparable.
        if judge.get("temperature") != 0:
            err(f"{path}: [judge].temperature = {judge.get('temperature')!r}, "
                "expected 0. This score is a training reward — a sampled judge "
                "makes the same submission score differently on a re-run.")

        t = judge.get("timeout")
        if not isinstance(t, (int, float)) or isinstance(t, bool) or t <= 0:
            err(f"{path}: [judge].timeout must be a positive number, got {t!r}.")

        w = judge.get("weight")
        if not isinstance(w, (int, float)) or isinstance(w, bool) or w <= 0:
            err(f"{path}: [judge].weight must be a positive number, got {w!r} — it "
                "is this dimension's share of the weighted mean.")
        else:
            weights[dim] = float(w)

        check_prompt_template(path, judge, path.parent, err)

        aggregation = (cfg.get("scoring") or {}).get("aggregation")
        if aggregation is not None and aggregation not in KNOWN_AGGREGATIONS:
            err(f"{path}: [scoring].aggregation = {aggregation!r} is not one of "
                f"{sorted(KNOWN_AGGREGATIONS)}.")

        check_playwright(path, cfg, err)
        ids = check_criteria(path, cfg, err, notes, MIN_CRITERIA_PER_DIMENSION)
        total_criteria += len(ids)
        for cid in ids:
            if cid in all_ids:
                err(f"{path}: criterion id {cid!r} is already used by the "
                    f"{all_ids[cid]!r} dimension. Ids must be unique across the "
                    "whole task — the score breakdown is keyed by id, so a repeat "
                    "collides and one of the two verdicts is lost.")
            else:
                all_ids[cid] = dim

    if total_criteria < MIN_CRITERIA_TOTAL:
        notes.append(f"{total_criteria} criteria across all dimensions. A small "
                     "product (a static page, a single-screen game) legitimately "
                     "needs few — but confirm they separate a working "
                     "implementation from a polished shell.")

    if weights:
        notes.append("dimension weights: "
                     + ", ".join(f"{d}={w:g}" for d, w in sorted(weights.items()))
                     + f" (total {sum(weights.values()):g}).")


def check_browser_rubric(task: Path, err, notes: list[str]) -> None:
    rdir = task / "tests" / "rubric" / "browser"
    path = rdir / "browser.toml"
    cfg = load_toml(path, err)
    if not cfg:
        return
    venv = verifier_env(task, err)

    judge = cfg.get("judge")
    if not isinstance(judge, dict):
        err(f"{path}: missing [judge].")
        return
    check_central_judge_keys(path, judge, venv, err)
    check_judge_key_set(path, judge, notes)
    mode = judge.get("mode")
    if not isinstance(mode, str) or not mode.strip():
        err(f"{path}: [judge].mode is required and must be a non-empty string, "
            f"got {mode!r}.")
    elif mode != "batched":
        notes.append(f"{path}: [judge].mode = {mode!r}, not \"batched\".")
    isolated = judge.get("isolated")
    if not isinstance(isolated, bool):
        err(f"{path}: [judge].isolated is required and must be a boolean, got "
            f"{isolated!r}.")
    elif isolated is not False:
        notes.append(f"{path}: [judge].isolated = {isolated!r}. An isolated judge "
                     "gets a fresh app per criterion.")
    check_prompt_template(path, judge, rdir, err)

    check_playwright(path, cfg, err)
    ids = check_criteria(path, cfg, err, notes, 12)
    weights = {c.get("weight") for c in criteria(cfg)}
    if len(weights) > 1:
        notes.append(f"criteria carry mixed weights {sorted(weights)}.")
    if ids:
        notes.append(f"{len(ids)} criteria in a single browser rubric.")


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    shape = task_shape(task)
    if shape == "dimensions":
        check_dimensions(task, err, notes)
    elif shape == "browser-rubric":
        check_browser_rubric(task, err, notes)
    else:
        err(f"{task}: no judge rubric found (see check-required-files).")

    return report("check-rubric-schema", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
