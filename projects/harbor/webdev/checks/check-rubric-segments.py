#!/usr/bin/env python3
"""tests/rubric/browser/segments.json must agree with browser.toml.

segments.json is how tests/test.py splits the rubric into one RewardKit
invocation per group against the same live database. test.py is deliberately
forgiving — an unusable segments.json falls back to running the rubric whole,
and criteria it does not list are appended to the LAST segment. Both fallbacks
are silent, and both change what is graded: an id typo turns a 33-segment run
into one 33-criterion session, which is exactly the failure mode segmenting
exists to prevent. So the agreement is checked here instead of discovered in a
score nobody can explain.

The file is optional. When it is absent this check is a no-op pass.
"""
from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.


def task_arg() -> Path:
    """The single positional argument: the task directory."""
    if len(sys.argv) < 2:
        sys.exit(f"usage: {Path(sys.argv[0]).name} <task-dir>")
    task = Path(sys.argv[1])
    if not task.is_dir():
        sys.exit(f"FATAL: {task} is not a directory")
    return task


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


def main() -> int:
    task = task_arg()
    errors: list[str] = []
    notes: list[str] = []
    err = make_err(errors)

    if sorted((task / "tests").glob("*/judge.toml")):
        print(f"NOTE {task}: dimensions-shaped task; segmenting does not apply "
              "(each dimension is already its own judge session).")
        print(f"check-rubric-segments: OK ({task})")
        return 0

    path = rubric_dir(task) / "segments.json"
    if not path.is_file():
        n = len(criteria(browser_config(task, err)))
        print(f"NOTE {task}: no segments.json - the whole rubric runs as ONE "
              f"batched judge session carrying all {n} criteria (supported).")
        if n >= 20:
            print(f"NOTE {task}: {n} criteria in a single session is the "
                  "configuration in which a judge has been observed reporting "
                  "verdicts from recalled context instead of gathered evidence, "
                  "and in which one timeout zeroes every criterion at once. If it "
                  "stays unsegmented, prompt.md must carry the "
                  "budget-exhaustion rule (see check-rubric-prompt).")
        print(f"check-rubric-segments: OK ({task})")
        return 0

    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        err(f"{path}: not valid JSON - {exc}. tests/test.py catches this and "
            "silently runs the whole rubric as ONE judge session.")
        return report("check-rubric-segments", task, errors, notes)

    rubric_ids = [c.get("id") for c in criteria(browser_config(task, err))
                  if isinstance(c.get("id"), str)]
    known = set(rubric_ids)

    segments = data.get("segments")
    if not isinstance(segments, list) or not segments:
        err(f"{path}: \"segments\" must be a non-empty list. test.py falls back to "
            "one whole-rubric session when it is missing or empty.")
        return report("check-rubric-segments", task, errors, notes)

    seen: dict[str, int] = {}
    restart_segments: list[str] = []
    for i, seg in enumerate(segments, 1):
        where = f"{path}: segment #{i}"
        if not isinstance(seg, dict):
            err(f"{where}: must be an object with \"id\" and \"criteria\".")
            continue
        sid = seg.get("id")
        if not isinstance(sid, str) or not sid.strip():
            err(f"{where}: missing a non-empty \"id\".")
        ids = seg.get("criteria")
        if not isinstance(ids, list) or not ids:
            err(f"{where} ({sid!r}): \"criteria\" must be a non-empty list of "
                "criterion ids from browser.toml.")
            continue
        if len(ids) > 1:
            notes.append(f"segment {sid!r} carries {len(ids)} criteria. A "
                         "per-invocation judge timeout zeroes every criterion in "
                         "the segment without judging any of them; one criterion "
                         "per segment keeps that blast radius at one id.")
        for cid in ids:
            if not isinstance(cid, str):
                err(f"{where} ({sid!r}): criterion entry {cid!r} is not a string.")
                continue
            if cid not in known:
                err(f"{where} ({sid!r}): criterion id {cid!r} does not exist in "
                    "browser.toml. test.py drops unknown ids silently; if none of "
                    "the listed ids match it runs the whole rubric as ONE session.")
            elif cid in seen:
                err(f"{where} ({sid!r}): criterion {cid!r} is already graded by "
                    f"segment #{seen[cid]}. A criterion judged twice is counted "
                    "twice in the weighted score.")
            else:
                seen[cid] = i
        if seg.get("restart_app"):
            restart_segments.append(str(sid))

    uncovered = [cid for cid in rubric_ids if cid not in seen]
    if uncovered:
        err(f"{path}: criteria not listed in any segment: {uncovered}. test.py "
            "appends them to the LAST segment, so they are graded by a judge "
            "session written for a different criterion — usually as fails.")

    if restart_segments:
        if len(restart_segments) > 1:
            notes.append(f"more than one segment sets restart_app "
                         f"({restart_segments}); each restart costs a full app "
                         "boot and health wait.")
        if restart_segments[-1] != str(segments[-1].get("id")):
            notes.append("the restart_app segment is not last. Restarting mid-run "
                         "is legitimate, but a persistence criterion is only "
                         "meaningful after every earlier write has landed.")
    else:
        notes.append("no segment sets restart_app. Nothing in this rubric then "
                     "survives a process restart, so in-memory state and "
                     "re-seed-on-boot both pass.")

    return report("check-rubric-segments", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
