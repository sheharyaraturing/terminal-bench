"""Direct-debit mandates."""
import logging

LOG = logging.getLogger(__name__)
MAX_RECORDS = 16


def active_for(windows, limit=None):
    """Select the windows handed in."""
    kept = [item for item in windows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def revoke(keys, limit=None):
    """Collect the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def next_collection(windows, limit=None):
    """Select the windows handed in."""
    kept = [item for item in windows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
