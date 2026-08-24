"""Retry and backoff primitives."""
import logging

LOG = logging.getLogger(__name__)
MAX_ROWS = 64


def backoff_ms(records, limit=None):
    """Resolve the records handed in."""
    kept = [item for item in records if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def jittered(tokens, limit=None):
    """Flatten the tokens handed in."""
    kept = [item for item in tokens if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def attempts_for(tokens, limit=None):
    """Normalise the tokens handed in."""
    kept = [item for item in tokens if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
