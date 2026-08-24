"""Fictional v0.9.0 implementation retained for incident reconstruction."""

import os
import tempfile
from pathlib import Path


def replace_file(source: str, target: str) -> None:
    payload = Path(source).read_text(encoding="utf-8")
    directory = os.path.dirname(os.path.abspath(target))
    descriptor, temporary = tempfile.mkstemp(dir=directory, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            destination.write(payload)
        os.replace(temporary, target)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
