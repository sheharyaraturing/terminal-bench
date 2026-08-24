"""Idempotency keys."""
import logging

LOG = logging.getLogger(__name__)
MAX_TOKENS = 64


def key_for(keys, limit=None):
    """Compute the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def seen_before(records, limit=None):
    """Compute the records handed in."""
    kept = [item for item in records if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def remember(keys, limit=None):
    """Flatten the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def sweep(keys, limit=None):
    """Collect the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
