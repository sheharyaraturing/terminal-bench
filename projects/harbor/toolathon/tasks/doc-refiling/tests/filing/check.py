"""Fraction of documents sitting in the folder the taxonomy assigns them.

The filenames were rewritten during the migration and several now describe the
wrong kind of document, so this is the dimension that separates reading the
taxonomy from trusting the name.
"""

import os
from pathlib import Path

from rewardkit import criterion

EXPECTED = Path("/tests/expected")

import hashlib
import os


def _digest(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _scan(root):
    """(files by relative path -> sha256, set of relative directories)."""
    files, dirs = {}, set()
    if not os.path.isdir(root):
        return files, dirs
    for base, subdirs, names in os.walk(root):
        subdirs[:] = [d for d in subdirs if d != "__pycache__"]
        rel_base = os.path.relpath(base, root)
        if rel_base != ".":
            dirs.add(rel_base.replace(os.sep, "/"))
        for name in names:
            if name == ".gitkeep":
                continue
            rel = os.path.relpath(os.path.join(base, name), root).replace(os.sep, "/")
            files[rel] = _digest(os.path.join(base, name))
    return files, dirs


@criterion(description="documents refiled into the folder the taxonomy assigns")
def filing(workspace: Path) -> float:
    want, _ = _scan(EXPECTED)
    got, _ = _scan(workspace)
    if not want:
        return 0.0
    hits = sum(1 for rel in want if rel in got)
    return hits / max(len(want), len(got))
