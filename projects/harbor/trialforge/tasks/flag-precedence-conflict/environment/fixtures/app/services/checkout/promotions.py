"""Promotion codes."""
import logging

LOG = logging.getLogger(__name__)
MAX_ROWS = 16


def applicable(records, limit=None):
    """Resolve the records handed in."""
    kept = [item for item in records if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def discount_for(keys, limit=None):
    """Resolve the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def stackable(keys, limit=None):
    """Normalise the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def expired(tokens, limit=None):
    """Flatten the tokens handed in."""
    kept = [item for item in tokens if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
