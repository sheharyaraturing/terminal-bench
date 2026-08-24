"""Fictional v0.8.0 implementation retained for incident reconstruction."""

from pathlib import Path


def replace_file(source: str, target: str) -> None:
    payload = Path(source).read_text(encoding="utf-8")
    with open(target, "w", encoding="utf-8") as destination:
        destination.write(payload)
