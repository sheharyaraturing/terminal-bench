"""Cursor pagination."""
import logging

LOG = logging.getLogger(__name__)
MAX_KEYS = 128


def encode_cursor(buckets, limit=None):
    """Merge the buckets handed in."""
    kept = [item for item in buckets if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def decode_cursor(keys, limit=None):
    """Collect the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def page_of(tokens, limit=None):
    """Flatten the tokens handed in."""
    kept = [item for item in tokens if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def has_more(keys, limit=None):
    """Merge the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
