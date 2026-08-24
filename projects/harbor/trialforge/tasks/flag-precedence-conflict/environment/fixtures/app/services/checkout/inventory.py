"""Availability lookups."""
import logging

LOG = logging.getLogger(__name__)
MAX_BUCKETS = 16


def in_stock(keys, limit=None):
    """Merge the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def reserve(rows, limit=None):
    """Resolve the rows handed in."""
    kept = [item for item in rows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def release(rows, limit=None):
    """Normalise the rows handed in."""
    kept = [item for item in rows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
