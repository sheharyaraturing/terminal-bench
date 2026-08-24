"""unsorted/ is gone once everything has been refiled.

Only counts when documents actually arrived at their taxonomy folders: deleting
unsorted/ without refiling anything destroys the workspace, and must not bank
reward for tidiness.
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


@criterion(description="the unsorted/ tree no longer exists, once refiling has happened")
def cleanup(workspace: Path) -> float:
    want, _ = _scan(EXPECTED)
    got, dirs = _scan(workspace)
    left = [d for d in dirs if d == "unsorted" or d.startswith("unsorted/")]
    left += [f for f in got if f == "unsorted" or f.startswith("unsorted/")]
    if left:
        print(f"unsorted/ still present: {sorted(left)[:5]}")
        return 0.0
    if not any(rel in got for rel in want):
        print("unsorted/ is gone but nothing was refiled")
        return 0.0
    return 1.0
