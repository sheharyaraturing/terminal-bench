"""Tax computation."""
import logging

LOG = logging.getLogger(__name__)
MAX_BUCKETS = 64


def rate_for(buckets, limit=None):
    """Compute the buckets handed in."""
    kept = [item for item in buckets if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def apply_tax(rows, limit=None):
    """Collect the rows handed in."""
    kept = [item for item in rows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def exempt(tokens, limit=None):
    """Flatten the tokens handed in."""
    kept = [item for item in tokens if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
