"""Upload handling.

Every endpoint here turns user-supplied strings into filesystem paths, so all
of it is load-bearing: filenames are reduced to a basename and matched against
an allowlist, and archive extraction is guarded against zip-slip.
"""
from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

MAX_FILE_BYTES = 20 * 1024 * 1024  # per uploaded file
MAX_ZIP_BYTES = 200 * 1024 * 1024  # total uncompressed size of a task archive
MAX_ZIP_ENTRIES = 5000

CHECK_SUFFIXES = (".sh", ".py")
RUBRIC_SUFFIXES = (".toml",)

_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SAFE_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class UploadError(ValueError):
    """Raised for anything the caller can fix by sending a different file."""


def safe_filename(name: str, allowed_suffixes: tuple[str, ...] | None = None) -> str:
    """Reduce an uploaded filename to a safe basename, or raise."""
    if not name:
        raise UploadError("missing filename")
    # Browsers and some clients send full paths; keep only the last segment and
    # reject anything that still looks like traversal.
    base = Path(name.replace("\\", "/")).name
    if base in ("", ".", "..") or not _SAFE_NAME_RE.match(base):
        raise UploadError(f"unsafe filename: {name!r}")
    if allowed_suffixes and Path(base).suffix.lower() not in allowed_suffixes:
        raise UploadError(
            f"unsupported file type: {base!r} (allowed: {', '.join(allowed_suffixes)})"
        )
    return base


def safe_task_id(task_id: str) -> str:
    if not isinstance(task_id, str) or not _SAFE_TASK_ID_RE.match(task_id) or task_id in (".", ".."):
        raise UploadError(f"unsafe task id: {task_id!r}")
    return task_id


def write_upload(
    dest_dir: Path,
    filename: str,
    data: bytes,
    allowed_suffixes: tuple[str, ...] | None = None,
    executable: bool = False,
) -> Path:
    if len(data) > MAX_FILE_BYTES:
        raise UploadError(
            f"{filename} is {len(data)} bytes, over the {MAX_FILE_BYTES}-byte limit"
        )
    name = safe_filename(filename, allowed_suffixes)
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / name
    path.write_bytes(data)
    if executable:
        # run_deterministic invokes checks through bash/python, but keeping the
        # bit set means they also work when run by hand.
        path.chmod(0o755)
    return path


def write_text(dest_path: Path, text: str) -> Path:
    if len(text.encode()) > MAX_FILE_BYTES:
        raise UploadError("content exceeds the size limit")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(text)
    return dest_path


def _zip_members(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    infos = [i for i in zf.infolist() if not i.filename.endswith("/")]
    if len(infos) > MAX_ZIP_ENTRIES:
        raise UploadError(f"archive has {len(infos)} entries, over the limit")
    total = sum(i.file_size for i in infos)
    if total > MAX_ZIP_BYTES:
        raise UploadError(f"archive expands to {total} bytes, over the limit")
    return infos


def _safe_member_path(name: str) -> Path:
    """Validate one archive member path; raise on absolute paths or traversal."""
    normalized = name.replace("\\", "/")
    p = Path(normalized)
    if p.is_absolute() or normalized.startswith("/"):
        raise UploadError(f"archive member has an absolute path: {name!r}")
    parts = [seg for seg in p.parts if seg not in ("", ".")]
    if any(seg == ".." for seg in parts):
        raise UploadError(f"archive member escapes the archive root: {name!r}")
    if not parts:
        raise UploadError(f"archive member has an empty path: {name!r}")
    return Path(*parts)


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    # Unix mode lives in the high 16 bits of external_attr; 0xA000 == S_IFLNK.
    return (info.external_attr >> 16) & 0xF000 == 0xA000


def _common_root(paths: list[Path]) -> str | None:
    """Return the single top-level directory shared by all members, if any."""
    roots = {p.parts[0] for p in paths if len(p.parts) > 1}
    if len(roots) == 1 and all(len(p.parts) > 1 for p in paths):
        return roots.pop()
    return None


def extract_zip_safely(zip_path: Path, dest_dir: Path, strip_common_root: bool = True) -> Path:
    """Extract an archive into dest_dir, rejecting traversal and symlinks.

    A zip that wraps everything in a single top-level directory (what you get
    from zipping a task folder) is unwrapped so dest_dir holds the task files
    directly.
    """
    if dest_dir.exists():
        raise UploadError(f"destination already exists: {dest_dir.name}")

    with zipfile.ZipFile(zip_path) as zf:
        infos = _zip_members(zf)
        if not infos:
            raise UploadError("archive is empty")
        members: list[tuple[zipfile.ZipInfo, Path]] = []
        for info in infos:
            if _is_symlink(info):
                raise UploadError(f"archive contains a symlink: {info.filename!r}")
            rel = _safe_member_path(info.filename)
            # Skip macOS Finder cruft rather than failing the whole upload.
            if rel.parts[0] == "__MACOSX" or rel.name == ".DS_Store":
                continue
            members.append((info, rel))
        if not members:
            raise UploadError("archive contains no usable files")

        strip = _common_root([rel for _, rel in members]) if strip_common_root else None

        dest_dir.mkdir(parents=True)
        try:
            for info, rel in members:
                target_rel = Path(*rel.parts[1:]) if strip else rel
                if not target_rel.parts:
                    continue
                target = dest_dir / target_rel
                # Belt and braces: confirm the resolved path is still inside dest.
                if not str(target.resolve()).startswith(str(dest_dir.resolve())):
                    raise UploadError(f"archive member escapes the destination: {info.filename!r}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, target.open("wb") as out:
                    shutil.copyfileobj(src, out, length=1024 * 1024)
        except Exception:
            shutil.rmtree(dest_dir, ignore_errors=True)
            raise
    return dest_dir
