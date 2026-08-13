#!/usr/bin/env python3
"""Print a human-readable summary of a rubric verdicts.json file.

Supports both Harbor pass/fail format and SkillBench/ServiceNow 1-5 score format.
Exits 0 if all applicable criteria pass, 1 otherwise.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: print-verdicts.py <verdicts.json>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 2

    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        print(f"error: invalid JSON: {exc}", file=sys.stderr)
        return 2

    checks = data.get("checks", data if isinstance(data, dict) else {})
    if not isinstance(checks, dict):
        print("error: verdicts.json missing 'checks' object", file=sys.stderr)
        return 2

    all_pass = True
    for name, entry in checks.items():
        if not isinstance(entry, dict):
            continue
        outcome = str(entry.get("outcome", entry.get("verdict", "fail"))).lower()
        score = entry.get("score")
        explanation = entry.get("explanation", entry.get("reason", ""))
        if outcome == "not_applicable":
            status = "N/A"
        elif outcome == "pass":
            status = "PASS"
        else:
            status = "FAIL"
            all_pass = False
        score_str = f" [{score}/5]" if score is not None else ""
        print(f"{status:4} {name}{score_str}: {explanation}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
