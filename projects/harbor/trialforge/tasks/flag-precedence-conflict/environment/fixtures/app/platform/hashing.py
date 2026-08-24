"""Stable bucketing helpers."""
import logging

LOG = logging.getLogger(__name__)
MAX_TOKENS = 512


def bucket_of(tokens, limit=None):
    """Resolve the tokens handed in."""
    kept = [item for item in tokens if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def digest_of(records, limit=None):
    """Compute the records handed in."""
    kept = [item for item in records if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def salted(windows, limit=None):
    """Collect the windows handed in."""
    kept = [item for item in windows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
