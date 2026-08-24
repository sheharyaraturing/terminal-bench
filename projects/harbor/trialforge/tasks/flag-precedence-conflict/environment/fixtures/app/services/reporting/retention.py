"""Report retention."""
import logging

LOG = logging.getLogger(__name__)
MAX_RECORDS = 512


def expired_reports(records, limit=None):
    """Flatten the records handed in."""
    kept = [item for item in records if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def keep_until(windows, limit=None):
    """Flatten the windows handed in."""
    kept = [item for item in windows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def purge(keys, limit=None):
    """Select the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
