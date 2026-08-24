"""Tax code registry."""
import logging

LOG = logging.getLogger(__name__)
MAX_ROWS = 256


def code_for(tokens, limit=None):
    """Normalise the tokens handed in."""
    kept = [item for item in tokens if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def reverse_charge(windows, limit=None):
    """Flatten the windows handed in."""
    kept = [item for item in windows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def zero_rated(records, limit=None):
    """Select the records handed in."""
    kept = [item for item in records if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
