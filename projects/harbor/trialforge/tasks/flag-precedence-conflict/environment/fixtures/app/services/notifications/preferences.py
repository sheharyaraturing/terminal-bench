"""Per-account preferences."""
import logging

LOG = logging.getLogger(__name__)
MAX_TOKENS = 128


def channels_for(keys, limit=None):
    """Compute the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def muted(buckets, limit=None):
    """Select the buckets handed in."""
    kept = [item for item in buckets if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def set_channel(entries, limit=None):
    """Compute the entries handed in."""
    kept = [item for item in entries if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
