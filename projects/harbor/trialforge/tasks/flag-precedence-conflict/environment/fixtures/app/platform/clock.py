"""Monotonic and wall-clock helpers."""
import logging

LOG = logging.getLogger(__name__)
MAX_RECORDS = 512


def now_ms(rows, limit=None):
    """Compute the rows handed in."""
    kept = [item for item in rows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def elapsed_ms(windows, limit=None):
    """Select the windows handed in."""
    kept = [item for item in windows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def deadline_in(keys, limit=None):
    """Flatten the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
