#!/usr/bin/env python3
"""The verifier must produce a reward on every exit path, and grade honestly.

Harbor requires a reward file however the verifier ends. Without one the trial
is reported as an infrastructure error rather than a scored 0.0 — thrown away
instead of counted, which quietly biases the benchmark toward submissions that
happen not to crash the verifier. Both shapes defend this twice: a placeholder
written before any real work, and a shell-level fallback that survives the
grading process dying outright.

The second concern is what gets graded. A verifier that reads the golden
solution, or that skips resetting state, is not measuring the submission.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# --- inlined helpers -------------------------------------------------------
# This check is standalone: it shares no module with its siblings, so it can
# be read, copied, or run on its own. The cost is a little duplication.

_TRIPLE_QUOTED_RE = re.compile(r'("""|\'\'\')(?:.|\n)*?\1')
_PY_COMMENT_RE = re.compile(r"(?m)#.*$")


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


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def join_continuations(text: str) -> str:
    """Collapse backslash continuations so a single-line regex can see a whole
    command. `printf '...' \\` + newline + `> "$LOG_DIR/reward.json"` is one
    statement, and matching it line-by-line reports a missing write that is
    plainly there."""
    out: list[str] = []
    buf = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        out.append(buf + line)
        buf = ""
    if buf:
        out.append(buf)
    return "\n".join(out)


def python_code_only(text: str) -> str:
    """Python source with docstrings and # comments gone, so a check hunting a
    forbidden reference does not fire on a comment explaining why the verifier
    does NOT do that."""
    return _PY_COMMENT_RE.sub("", _TRIPLE_QUOTED_RE.sub("", text))


def shell_hygiene(path: Path, err) -> None:
    """Parse and line-ending checks shared by every shell entrypoint.

    A CRLF line ending is the nastiest of these: the shell reads
    `set -euo pipefail\r` as a command named `pipefail\r`, the script dies on
    line 2, and the failure surfaces as a missing reward file that names
    nothing. It is invisible in every editor and in most diffs.
    """
    raw = path.read_bytes() if path.is_file() else b""
    if b"\r\n" in raw:
        line = raw.split(b"\r\n")[0][:60].decode("utf-8", "replace")
        err(f"{path}: has CRLF line endings (first: {line!r}...). The shell reads "
            "the carriage return as part of the command, so the script dies "
            "immediately and the run reports a missing reward rather than an "
            "error anyone can act on. Convert to LF.")
    if raw and not raw.startswith(b"#!"):
        err(f"{path}: no shebang line.")
    proc = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        err(f"{path}: is not valid bash - {detail[0] if detail else 'parse error'}")


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


def check_test_sh(path: Path, sh: str, err, notes: list[str], *,
                  must_run_test_py: bool) -> None:
    """The outermost safety net, shared by both shapes."""
    if not sh.strip():
        err(f"{path}: missing or empty — it is Harbor's verifier entrypoint.")
        return

    shell_hygiene(path, err)

    # Both files, and both with a zero value. Merely mentioning reward.txt is
    # not a fallback: a `test -s` guard that never writes still leaves Harbor
    # with nothing to read.
    joined = join_continuations(sh)
    for name in ("reward.txt", "reward.json"):
        writes = re.search(
            rf"(?:printf|echo|cat|tee)[^\n]*0\.0[^\n]*{re.escape(name)}"
            rf"|(?:printf|echo)[^\n]*0\.0[^\n]*>\s*\"?\$?\{{?\w*\}}?/?{re.escape(name)}",
            joined)
        if not writes:
            err(f"{path}: no zero-reward write for {name}. If the grading process "
                "dies before its own placeholder (missing interpreter, import "
                "error, OOM kill), Harbor finds no reward and reports "
                "RewardFileNotFoundError instead of a scored 0.0.")

    # `exec` replaces the shell, so a trap or any trailing fallback never runs.
    if re.search(r"^\s*exec\s+(python3?|rewardkit)\b", sh, re.MULTILINE):
        err(f"{path}: uses `exec`, which replaces the shell — the EXIT trap and "
            "everything after it never run, so the fallback reward write is dead.")

    # `set -e` plus an unguarded grading call aborts before the fallback, which
    # is the exact path the fallback exists to cover.
    if re.search(r"^\s*set\s+-[a-zA-Z]*e", sh, re.MULTILINE) and "trap " not in sh:
        notes.append(f"{path}: `set -e` without a `trap ... EXIT`. A non-zero exit "
                     "from the grading step aborts before any trailing fallback — "
                     "harmless if the zero-reward write happens up front, fatal if "
                     "it is at the end.")

    if must_run_test_py and not re.search(r"\btest\.py\b", sh):
        err(f"{path}: never runs tests/test.py, where all the verifier logic for "
            "this shape lives.")


def check_dimensions(task: Path, err, notes: list[str]) -> None:
    path = task / "tests" / "test.sh"
    sh = read_text(path)
    check_test_sh(path, sh, err, notes, must_run_test_py=False)
    if not sh.strip():
        return

    if not re.search(r"\brewardkit\b", sh):
        err(f"{path}: never invokes rewardkit. rewardkit is what discovers the "
            "dimension judges, calls them, and writes the reward; without it the "
            "verifier grades nothing.")

    # The judge needs a served page. Judging before the app answers turns a slow
    # boot into a rubric-wide zero that looks like a broken submission.
    probe = re.search(r"health|urlopen|curl|wget|nc -z", sh)
    grade = re.search(r"\brewardkit\b", sh)
    if not probe:
        err(f"{path}: no readiness probe before grading. A submission that boots "
            "slowly is judged against a connection-refused page and scores 0 on "
            "every dimension for a reason unrelated to its code.")
    elif grade and probe.start() > grade.start():
        err(f"{path}: the readiness probe appears after rewardkit is invoked. The "
            "judges reach the app before it is listening, so a slow boot reads as "
            "a broken app.")

    if not re.search(r"/logs/verifier|VERIFIER_LOG_DIR", sh):
        notes.append("tests/test.sh does not reference the verifier log dir; "
                     "confirm the reward lands where Harbor reads it.")


def check_browser_rubric(task: Path, err, notes: list[str]) -> None:
    sh_path = task / "tests" / "test.sh"
    py_path = task / "tests" / "test.py"
    check_test_sh(sh_path, read_text(sh_path), err, notes, must_run_test_py=True)

    py = read_text(py_path)
    if not py.strip():
        err(f"{py_path}: missing or empty.")
        return

    for name in ("reward.txt", "reward.json"):
        if name not in py:
            err(f"{py_path}: never writes {name}. Harbor reads reward.json and "
                "falls back to reward.txt; both must be produced.")
    if "report.json" not in py:
        notes.append("tests/test.py does not mention report.json; the "
                     "human-readable breakdown is what makes a 0.0 diagnosable.")
    if not re.search(r"rewardkit", py, re.IGNORECASE):
        err(f"{py_path}: never invokes RewardKit.")

    # Grading the database the agent left behind lets a submission pre-stage the
    # rows the rubric looks for instead of implementing the writes.
    code = python_code_only(py)

    # A *call*, not a mention and not the definition. `.db` also appears in glob
    # lists and comments, and a `def wipe_db(...)` left behind after its call
    # site was deleted still looks like a wipe to a naive search — so drop the
    # def lines before looking for an invocation.
    calls_only = re.sub(r"(?m)^\s*def\s+\w+\s*\([^)]*\)[^\n]*$", "", code)
    # The call has to be a wipe OF THE DATABASE. A bare `unlink(` or
    # `shutil.rmtree(` matches the source snapshot and the log-dir cleanup, so
    # matching those reported a wipe that was no longer being performed.
    wipes = re.search(
        r"\b\w*(?:wipe|reset|purge|clear|drop)_?(?:db|database|data)\w*\s*\("
        r"|(?:unlink|rmtree|remove|os\.remove)\s*\([^)\n]*\.(?:db|sqlite|sqlite3)"
        r"|rm\s+-[a-z]*f[^\n]*\.(?:db|sqlite|sqlite3)",
        calls_only)
    if not wipes:
        notes.append(f"{py_path}: no database wipe before grading. The judge then "
                     "sees whatever state the agent left behind, which lets a "
                     "submission pre-stage the rows the rubric looks for instead of "
                     "implementing the writes.")

    if not re.search(r"snapshot_app_source|app-source|app_source", py):
        notes.append("tests/test.py does not snapshot the delivered app source; "
                     "that copy is usually the only one that outlives a failed "
                     "trial.")

    for pattern, why in (
        (r"/solution\b", "reads /solution — grading the golden app scores the "
                         "oracle rather than the submission"),
        (r"\bsolve\.sh\b", "runs solve.sh — the verifier must grade what the agent "
                           "delivered, not install the golden solution"),
    ):
        if re.search(pattern, code):
            err(f"{py_path}: {why}.")

    if re.search(r"urlopen\([^)]*/api/|requests\.(get|post)\([^)]*/api/", code):
        notes.append("tests/test.py appears to call the app's API directly. No "
                     "endpoint paths are prescribed to the agent, so a hard-coded "
                     "route fails correct submissions that chose different ones.")


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
        err(f"{task}: no recognisable verifier (see check-required-files).")

    return report("check-verifier-contract", task, errors, notes)


if __name__ == "__main__":
    raise SystemExit(main())
