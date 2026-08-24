"""Fictional v0.8.1 implementation retained for incident reconstruction."""

import os
from pathlib import Path


def replace_file(source: str, target: str) -> None:
    payload = Path(source).read_text(encoding="utf-8")
    if os.path.lexists(target):
        os.unlink(target)
    with open(target, "w", encoding="utf-8") as destination:
        destination.write(payload)
