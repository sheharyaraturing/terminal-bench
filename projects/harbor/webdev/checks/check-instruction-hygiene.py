#!/usr/bin/env python3
"""instruction.md (and the /instructions brief) must not leak the rubric.

The agent brief and the browser rubric are adversarial documents. The brief is
deliberately written as field notes and complaints so that working out what the
software must guarantee is the task; the rubric names the exact fixtures and
probes that decide the score. A brief that quotes the rubric — a criterion id, a
verbatim criterion sentence, an endpoint path the judge forges against — turns
the task from "infer the invariants" into "implement this checklist", and the
scores stop measuring what the difficulty_explanation claims they measure.

This check is mechanical: it looks for rubric identifiers and long verbatim
overlaps. It cannot tell whether the prose gives too much away.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.


def load_toml(path: Path, err) -> dict:
    """Parse TOML with the same parser Harbor/RewardKit use. Errors go to err."""
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


def rubric_dir(task: Path) -> Path:
    return task / "tests" / "rubric" / "browser"


def browser_config(task: Path, err) -> dict:
    return load_toml(rubric_dir(task) / "browser.toml", err)


def criteria(browser_cfg: dict) -> list[dict]:
    blocks = browser_cfg.get("criterion")
    if not isinstance(blocks, list):
        return []
    return [c for c in blocks if isinstance(c, dict)]


def make_err(errors: list[str]):
    def err(msg: str) -> None:
        errors.append(msg)

    return err


def report(name: str, task: Path, errors: list[str], notes: list[str]) -> int:
    """Print a uniform per-check report and return the process exit code."""
    for n in notes:
        print(f"NOTE {task}: {n}")
    if errors:
        for e in errors:
            print(f"FAIL {e}")
        print(f"{name}: {len(errors)} problem(s)")
        return 1
    print(f"{name}: OK ({task})")
    return 0


def task_arg() -> Path:
    """The single positional argument: the task directory."""
    if len(sys.argv) < 2:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <task-dir>")
    task = Path(sys.argv[1])
    if not task.is_dir():
        sys.exit(f"FATAL: {task} is not a directory")
    return task
# Sentence-length shingles; short overlaps ("the invoice total") are noise.
SHINGLE_WORDS = 12
MIN_INSTRUCTION_CHARS = 500

# Grader machinery the prompt must never name. Naming it makes the agent write
# to the rubric instead of building the product. Each entry needs a
# grader-context neighbour so ordinary English survives: "test accounts",
# "check the totals", and "the dimension of the card" are all legitimate.
GRADER_VOCAB = [
    # (pattern, what it names, hard) — hard=True blocks the task; hard=False is
    # advisory, for terms that also have ordinary product meanings.
    (re.compile(r"\brewardkit\b", re.I), "the grading runner", True),
    (re.compile(r"\b(reward|judge)\.toml\b", re.I), "a grader config file", True),
    (re.compile(r"\btests?/test\.sh\b", re.I), "the verifier entrypoint", True),
    (re.compile(r"(?<![\w/])/tests(?:/|\b)"), "the grading directory", True),
    (re.compile(r"\byou will be (?:scored|graded|judged)\b", re.I),
     "an explicit statement that the work is graded", True),
    (re.compile(r"\bJUDGE[-_][A-Z0-9]"), "a grader sentinel value", True),
    (re.compile(r"\bplaywright\b", re.I), "the judge's browser driver", False),
    (re.compile(r"\bopenrouter\b", re.I), "the judge's model provider", False),
    (re.compile(r"\bharbor\b", re.I), "the benchmark harness", False),
    (re.compile(r"\bpass bar\b", re.I), "rubric vocabulary", False),
    (re.compile(r"\b(?:the )?(?:oracle|verifier)\b(?=[^.]{0,60}"
                r"(?:score|grade|run|check|pass))", re.I), "benchmark vocabulary", False),
    (re.compile(r"\bcriteri(?:on|a)\b(?=[^.]{0,60}"
                r"(?:score|grade|judge|pass|weight))", re.I), "rubric vocabulary", False),
    (re.compile(r"\bdimension\b(?=[^.]{0,60}(?:score|grade|judge|weight))", re.I),
     "rubric vocabulary", False),
]

PLACEHOLDER_RE = re.compile(r"CHANGE-ME|TODO:|FIXME|XXX:|\{\{[a-z_]+\}\}|"
                            r"<INSERT|LOREM IPSUM", re.IGNORECASE)


def shingles(text: str, n: int = SHINGLE_WORDS) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    root_instruction = task / "instruction.md"
    brief_files = [root_instruction]
    instructions_dir = task / "environment" / "instructions"
    if instructions_dir.is_dir():
        brief_files += sorted(instructions_dir.rglob("*.md"))

    root_text = read_text(root_instruction)
    if len(root_text.strip()) < MIN_INSTRUCTION_CHARS and not instructions_dir.is_dir():
        err(f"{root_instruction}: only {len(root_text.strip())} chars and there is "
            "no environment/instructions/ brief. The agent has nothing to build "
            "from.")

    for f in brief_files:
        text = read_text(f)
        for m in PLACEHOLDER_RE.finditer(text):
            err(f"{f}: unfinished placeholder {m.group(0)!r} — the brief still "
                "carries template scaffolding.")

    # ---- rubric leakage -----------------------------------------------------
    judge_files = sorted((task / "tests").glob("*/judge.toml"))
    rubric_configs = ([load_toml(jf, err) for jf in judge_files] if judge_files
                      else [browser_config(task, err)])
    ids = [c.get("id") for cfg in rubric_configs for c in criteria(cfg)
           if isinstance(c.get("id"), str)]

    # Compare against criterion DESCRIPTIONS only, not the whole rubric.
    # A judge prompt necessarily restates app facts the brief also states —
    # the demo accounts, the base URL, the seeded record names — because both
    # sides need them. That overlap is shared fixture data, not leakage. What
    # must never appear in the brief is the wording of a criterion, which is
    # what turns "infer the invariants" into "implement this checklist".
    rubric_shingles: set[str] = set()
    for cfg in rubric_configs:
        for c in criteria(cfg):
            rubric_shingles |= shingles(str(c.get("description", "")))

    for f in brief_files:
        text = read_text(f)
        for cid in ids:
            # Criterion ids are snake_case and would never occur naturally in a
            # shop-floor narrative.
            if re.search(rf"\b{re.escape(cid)}\b", text):
                err(f"{f}: contains the rubric criterion id {cid!r}. The brief is "
                    "supposed to state symptoms, not name the checks; an id in the "
                    "brief tells the agent exactly which probe decides its score.")
        overlap = shingles(text) & rubric_shingles
        if overlap:
            sample = sorted(overlap)[:2]
            # Advisory: a prompt and a criterion legitimately share product
            # vocabulary, and a long shared phrase is suspicious rather than
            # certainly wrong.
            notes.append(f"{f}: shares {len(overlap)} verbatim {SHINGLE_WORDS}-word "
                         f"passage(s) with a criterion description, e.g. {sample!r}. "
                         "Check it is shared product vocabulary and not rubric "
                         "wording copied into the brief.")

    # ---- grader machinery ---------------------------------------------------
    # Only instruction.md: the /instructions brief of the older shape is the
    # same document split by topic, so scan it too when it exists.
    for f in brief_files:
        text = read_text(f)
        for pattern, what, hard in GRADER_VOCAB:
            for m in pattern.finditer(text):
                line = text[:m.start()].count("\n") + 1
                message = (f"{f}:{line}: names {what} ({m.group(0)!r}). The prompt "
                           "is a product request; naming the grading machinery "
                           "tells the agent to write to the rubric instead of "
                           "building the app.")
                # Only terms that cannot plausibly be product vocabulary block a
                # task. "harbor", "dimension", "oracle" and friends all have
                # ordinary meanings a real product brief might use.
                (err if hard else notes.append)(message)

    # ---- endpoint prescription ---------------------------------------------
    # No HTTP paths are prescribed anywhere in these tasks — that is what makes
    # the judge's "discover the endpoint from UI traffic" probes meaningful. A
    # brief that names routes hands the judge's discovery step to the agent.
    for f in brief_files:
        text = read_text(f)
        routes = set(re.findall(r"(?<![\w/])/api/[A-Za-z0-9._/{}:-]+", text))
        if routes:
            notes.append(f"{f} names concrete API routes {sorted(routes)[:4]}. Both "
                         "shipped tasks deliberately prescribe no endpoint paths so "
                         "the agent must design its own API and the judge must "
                         "discover it; confirm this is intentional.")

    # ---- solution leakage ---------------------------------------------------
    for f in brief_files:
        text = read_text(f)
        for bad in ("solution/app", "/solution", "solve.sh", "APP_MANIFEST.md.golden"):
            if bad in text:
                err(f"{f}: mentions {bad!r} — the golden solution's location must "
                    "not appear in the agent brief.")

    return report("check-instruction-hygiene", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
