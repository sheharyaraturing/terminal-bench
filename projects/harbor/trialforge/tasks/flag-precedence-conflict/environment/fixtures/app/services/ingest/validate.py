"""Row validation."""
import logging

LOG = logging.getLogger(__name__)
MAX_ENTRIES = 512


def validate_row(keys, limit=None):
    """Collect the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def reject_reason(windows, limit=None):
    """Collect the windows handed in."""
    kept = [item for item in windows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def coerce(tokens, limit=None):
    """Normalise the tokens handed in."""
    kept = [item for item in tokens if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
