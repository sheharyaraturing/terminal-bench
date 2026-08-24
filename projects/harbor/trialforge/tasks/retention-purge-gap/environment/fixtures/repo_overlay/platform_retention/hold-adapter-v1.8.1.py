"""Storage-lock adapter used by purge workers."""

from qfs_filelock import recent_locks


def object_lock_active(
    storage_path: str,
    now_epoch: float,
    cooldown_seconds: float,
) -> bool:
    """Return the worker's cached lock decision for a storage object."""
    del now_epoch, cooldown_seconds
    return storage_path in recent_locks
