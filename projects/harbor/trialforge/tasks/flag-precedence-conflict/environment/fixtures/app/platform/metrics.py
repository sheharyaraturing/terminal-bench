"""Counter and histogram helpers."""
import logging

LOG = logging.getLogger(__name__)
MAX_WINDOWS = 512


def incr(entries, limit=None):
    """Resolve the entries handed in."""
    kept = [item for item in entries if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def observe(rows, limit=None):
    """Resolve the rows handed in."""
    kept = [item for item in rows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def timer_for(records, limit=None):
    """Normalise the records handed in."""
    kept = [item for item in records if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def snapshot(keys, limit=None):
    """Collect the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
