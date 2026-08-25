#!/usr/bin/env python3
"""Generate a self-contained index.html viewer for terminal-bench run results.

Two-file design: this script reads <runs>/<run_id>/report.json (+ status.json)
and injects the data into template.html (which must sit next to this script),
writing index.html into the runs directory.

Usage:
  python build_index.py [runs_dir]
    runs_dir defaults to the directory this script lives in.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE = SCRIPT_DIR / 'template.html'


def load_runs(runs_dir: Path) -> list:
    runs = []
    for child in sorted(runs_dir.iterdir()):
        if not child.is_dir():
            continue
        report_path = child / 'report.json'
        if not report_path.exists():
            continue
        try:
            report = json.loads(report_path.read_text())
        except Exception as e:
            print(f'skip {child.name}: bad report.json ({e})')
            continue
        status = {}
        status_path = child / 'status.json'
        if status_path.exists():
            try:
                status = json.loads(status_path.read_text())
            except Exception:
                status = {}
        runs.append({'run_id': child.name, 'report': report, 'status': status})
    return runs


def main() -> int:
    runs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else SCRIPT_DIR
    runs_dir = runs_dir.resolve()
    if not TEMPLATE.is_file():
        print(f'error: template.html not found next to build_index.py ({TEMPLATE})')
        return 1
    runs = load_runs(runs_dir)
    if not runs:
        print(f'no runs with report.json found under {runs_dir}')
        return 1
    tpl = TEMPLATE.read_text()
    payload = json.dumps(runs, ensure_ascii=False)
    html = tpl.replace('__RUNS_DATA__', payload)
    out = runs_dir / 'index.html'
    out.write_text(html)
    print(f'wrote {out} ({len(runs)} runs, {out.stat().st_size} bytes)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
