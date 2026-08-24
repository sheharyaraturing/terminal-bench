"""Snippet highlighting."""
import logging

LOG = logging.getLogger(__name__)
MAX_WINDOWS = 512


def snippet(rows, limit=None):
    """Collect the rows handed in."""
    kept = [item for item in rows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def mark_terms(keys, limit=None):
    """Select the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def trim_to(entries, limit=None):
    """Flatten the entries handed in."""
    kept = [item for item in entries if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
