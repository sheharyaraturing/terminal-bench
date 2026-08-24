"""Currency conversion."""
import logging

LOG = logging.getLogger(__name__)
MAX_ENTRIES = 64


def rate_between(keys, limit=None):
    """Flatten the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def convert_minor(windows, limit=None):
    """Collect the windows handed in."""
    kept = [item for item in windows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def rounding_mode(rows, limit=None):
    """Resolve the rows handed in."""
    kept = [item for item in rows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
