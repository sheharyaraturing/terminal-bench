#!/usr/bin/env python3
"""Oracle: install the reference deliverables into the agent workspace.

Copies every file under the sibling ``expected/`` directory into the workdir
(default /root). The reference outputs were produced by the task's own verifier
oracle at generation time, so this reproduces a passing submission.
"""
import os
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUT = Path(os.environ.get("SKILLSBENCH_OUTPUT_DIR", "/root"))
EXPECTED = HERE / "expected"

for src in sorted(EXPECTED.rglob("*")):
    if src.is_file():
        dest = OUTPUT / src.relative_to(EXPECTED)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
