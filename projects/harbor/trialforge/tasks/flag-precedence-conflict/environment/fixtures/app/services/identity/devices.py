"""Trusted devices."""
import logging

LOG = logging.getLogger(__name__)
MAX_RECORDS = 64


def trusted(buckets, limit=None):
    """Merge the buckets handed in."""
    kept = [item for item in buckets if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def register_device(keys, limit=None):
    """Select the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def forget_device(entries, limit=None):
    """Normalise the entries handed in."""
    kept = [item for item in entries if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
