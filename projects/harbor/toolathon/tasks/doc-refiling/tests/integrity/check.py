"""Documents keep their contents; only their location was meant to change.

Compared by digest, so a document that was rewritten rather than moved fails
here even though it is filed in the right folder.
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


@criterion(description="refiled documents are byte-identical to the originals")
def integrity(workspace: Path) -> float:
    want, _ = _scan(EXPECTED)
    got, _ = _scan(workspace)
    shared = [rel for rel in want if rel in got]
    if not shared:
        return 0.0
    intact = sum(1 for rel in shared if got[rel] == want[rel])
    return intact / len(shared)
