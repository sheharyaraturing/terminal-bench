"""Ingest watermarks."""
import logging

LOG = logging.getLogger(__name__)
MAX_KEYS = 64


def high_water(windows, limit=None):
    """Select the windows handed in."""
    kept = [item for item in windows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def advance(entries, limit=None):
    """Select the entries handed in."""
    kept = [item for item in entries if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def lagging_partitions(records, limit=None):
    """Collect the records handed in."""
    kept = [item for item in records if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
