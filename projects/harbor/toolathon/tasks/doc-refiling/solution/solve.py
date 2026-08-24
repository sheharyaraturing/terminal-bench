from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

HEADER = re.compile(r"^Document-Type:\s*(.+?)\s*$", re.MULTILINE)
ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*`([^`]+)`\s*\|$", re.MULTILINE)
BULLET = re.compile(r"^-\s*`([^`]+)`\s*$", re.MULTILINE)

def taxonomy(ws: Path) -> tuple[list[str], dict[str, str]]:
    text = (ws / "taxonomy.md").read_text()
    buckets = BULLET.findall(text)
    mapping = {}
    for doc_type, bucket in ROW.findall(text):
        if doc_type.lower().startswith("document-type"):
            continue
        mapping[doc_type.strip()] = bucket.strip()
    return buckets, mapping

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    ws = Path(args.workspace)

    buckets, mapping = taxonomy(ws)
    for bucket in buckets:
        (ws / bucket).mkdir(parents=True, exist_ok=True)

    moved = 0
    for path in sorted((ws / "unsorted").rglob("*")):
        if not path.is_file():
            continue
        match = HEADER.search(path.read_text(errors="replace"))
        if not match:
            continue
        bucket = mapping.get(match.group(1).strip())
        if not bucket:
            continue
        shutil.move(str(path), str(ws / bucket / path.name))
        moved += 1

    shutil.rmtree(ws / "unsorted", ignore_errors=True)
    print(f"refiled {moved} documents into {len(buckets)} folders")

if __name__ == "__main__":
    main()
