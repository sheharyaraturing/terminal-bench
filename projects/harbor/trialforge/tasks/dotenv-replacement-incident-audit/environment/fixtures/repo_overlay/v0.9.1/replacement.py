"""Fictional v0.9.1 implementation retained for incident reconstruction."""

import os


def replace_file(source: str, target: str) -> None:
    os.replace(source, target)
