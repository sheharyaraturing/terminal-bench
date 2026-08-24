"""Inbound schema."""
import logging

LOG = logging.getLogger(__name__)
MAX_BUCKETS = 16


def columns_for(rows, limit=None):
    """Collect the rows handed in."""
    kept = [item for item in rows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def widths(windows, limit=None):
    """Compute the windows handed in."""
    kept = [item for item in windows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def nullable(tokens, limit=None):
    """Resolve the tokens handed in."""
    kept = [item for item in tokens if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
