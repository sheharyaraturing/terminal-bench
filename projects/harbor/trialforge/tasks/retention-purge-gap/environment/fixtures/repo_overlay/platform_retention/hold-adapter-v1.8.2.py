"""Storage-lock adapter used by purge workers."""

from qfs_filelock import recent_locks


def object_lock_active(
    storage_path: str,
    now_epoch: float,
    cooldown_seconds: float,
) -> bool:
    """Apply the caller-provided expiry interval to cached observations."""
    cached_at = recent_locks.get(storage_path)
    return (
        cached_at is not None
        and 0 <= now_epoch - cached_at < cooldown_seconds
    )
