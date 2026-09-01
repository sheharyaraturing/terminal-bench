#!/usr/bin/env python3
"""The judge rubric's mechanical contract, for whichever shape the task uses.

Current format: one tests/<dimension>/judge.toml per graded dimension, each a
self-contained judge with an inline prompt_template and its own criteria.
Earlier format: a single tests/rubric/browser/browser.toml.

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
    task_cfg = load_toml(task / "task.toml", err)
    venv = (task_cfg.get("verifier") or {}).get("env") or {}
    want_judge, want_model = venv.get("REWARDKIT_JUDGE"), venv.get("REWARDKIT_MODEL")

    # A dimension directory with no judge.toml is a dimension that silently
    # contributes nothing to the weighted mean.
    for d in sorted((task / "tests").iterdir()):
        if d.is_dir() and d.name != "rubric" and not (d / "judge.toml").is_file():
            err(f"{d}: dimension directory has no judge.toml, so rewardkit "
                "discovers nothing here and the dimension contributes nothing.")

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

        # One driver and one model across every dimension: a per-dimension drift
        # means the reward is a blend of two graders nobody intended to compare.
        if want_judge and judge.get("judge") != want_judge:
            err(f"{path}: [judge].judge = {judge.get('judge')!r} but task.toml sets "
                f"REWARDKIT_JUDGE = {want_judge!r}.")
        if want_model and judge.get("model") != want_model:
            err(f"{path}: [judge].model = {judge.get('model')!r} but task.toml sets "
                f"REWARDKIT_MODEL = {want_model!r}.")

        if judge.get("mode") != "batched":
            notes.append(f"{path}: [judge].mode = {judge.get('mode')!r}, not "
                         "\"batched\". Splitting a dimension is allowed; just "
                         "confirm no criterion depends on what an earlier one "
                         "wrote.")
        if judge.get("isolated") is not False:
            notes.append(f"{path}: [judge].isolated = {judge.get('isolated')!r}. "
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

        template = judge.get("prompt_template")
        if not isinstance(template, str) or not template.strip():
            err(f"{path}: [judge].prompt_template is required and must be the "
                "inline prompt for this dimension.")
        elif CRITERIA_PLACEHOLDER not in template:
            err(f"{path}: [judge].prompt_template has no {CRITERIA_PLACEHOLDER} "
                "placeholder. RewardKit substitutes the criteria there; without it "
                "the judge is handed a prompt with NO criteria and scores on "
                "nothing.")

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
    task_cfg = load_toml(task / "task.toml", err)
    venv = (task_cfg.get("verifier") or {}).get("env") or {}

    judge = cfg.get("judge")
    if not isinstance(judge, dict):
        err(f"{path}: missing [judge].")
        return
    if venv.get("REWARDKIT_JUDGE") and judge.get("judge") != venv["REWARDKIT_JUDGE"]:
        err(f"{path}: [judge].judge = {judge.get('judge')!r} but task.toml sets "
            f"REWARDKIT_JUDGE = {venv['REWARDKIT_JUDGE']!r}.")
    if venv.get("REWARDKIT_MODEL") and judge.get("model") != venv["REWARDKIT_MODEL"]:
        err(f"{path}: [judge].model = {judge.get('model')!r} but task.toml sets "
            f"REWARDKIT_MODEL = {venv['REWARDKIT_MODEL']!r}.")
    if judge.get("mode") != "batched":
        err(f"{path}: [judge].mode = {judge.get('mode')!r}, expected \"batched\".")
    if judge.get("isolated") is not False:
        err(f"{path}: [judge].isolated = {judge.get('isolated')!r}, expected false.")
    template = judge.get("prompt_template")
    if not template:
        err(f"{path}: [judge].prompt_template is required.")
    elif not (rdir / template).is_file():
        err(f"{path}: [judge].prompt_template = {template!r} does not exist at "
            f"{rdir / template}.")

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
