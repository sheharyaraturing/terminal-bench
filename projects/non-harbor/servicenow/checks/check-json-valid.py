#!/usr/bin/env python3
"""ServiceNow deterministic check: task JSON is valid and has required fields."""
import json
import sys
from pathlib import Path

def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check-json-valid.py <task.json>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"FAIL: {path} not found")
        return 1
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        print(f"FAIL: invalid JSON: {exc}")
        return 1
    missing = [k for k in ("task_id", "executions") if k not in data]
    if missing:
        print(f"FAIL: missing keys: {missing}")
        return 1
    print("PASS")
    return 0

if __name__ == "__main__":
    sys.exit(main())
