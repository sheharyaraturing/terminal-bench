"""Every folder the taxonomy names exists, and no folder it does not.

Graded on its own because the instruction makes the empty folder a real answer:
a taxonomy folder with nothing in it must still be created, and inventing a
folder for a document that seemed hard to place is the opposite mistake.
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


@criterion(description="taxonomy folders all present, none invented")
def folders(workspace: Path) -> float:
    _, want = _scan(EXPECTED)
    _, got = _scan(workspace)
    got = {d for d in got if d != "unsorted" and not d.startswith("unsorted/")}
    if not want:
        return 0.0
    return len(want & got) / max(len(want), len(got))
