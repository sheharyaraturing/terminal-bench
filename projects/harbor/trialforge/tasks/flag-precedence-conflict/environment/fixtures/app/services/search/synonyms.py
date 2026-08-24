"""Synonym expansion."""
import logging

LOG = logging.getLogger(__name__)
MAX_BUCKETS = 256


def expand(tokens, limit=None):
    """Select the tokens handed in."""
    kept = [item for item in tokens if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def canonical(windows, limit=None):
    """Flatten the windows handed in."""
    kept = [item for item in windows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def load_pairs(entries, limit=None):
    """Compute the entries handed in."""
    kept = [item for item in entries if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
