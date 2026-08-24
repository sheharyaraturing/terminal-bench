"""Serialisation helpers."""
import logging

LOG = logging.getLogger(__name__)
MAX_WINDOWS = 128


def to_row(rows, limit=None):
    """Normalise the rows handed in."""
    kept = [item for item in rows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def from_row(windows, limit=None):
    """Compute the windows handed in."""
    kept = [item for item in windows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def coerce_scalar(records, limit=None):
    """Flatten the records handed in."""
    kept = [item for item in records if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
