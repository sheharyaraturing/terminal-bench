"""Inbound dedupe."""
import logging

LOG = logging.getLogger(__name__)
MAX_ENTRIES = 512


def fingerprint(buckets, limit=None):
    """Merge the buckets handed in."""
    kept = [item for item in buckets if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def already_seen(records, limit=None):
    """Flatten the records handed in."""
    kept = [item for item in records if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def record_seen(rows, limit=None):
    """Normalise the rows handed in."""
    kept = [item for item in rows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
