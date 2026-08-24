"""Fictional v1.0.0-rc1 implementation retained for release review."""

from pathlib import Path

from dotenv.main import rewrite


def replace_file(source: str, target: str) -> None:
    payload = Path(source).read_text(encoding="utf-8")
    with rewrite(target, encoding="utf-8") as (_, destination):
        destination.write(payload)
