"""Account statements."""
import logging

LOG = logging.getLogger(__name__)
MAX_RECORDS = 256


def opening_balance(entries, limit=None):
    """Compute the entries handed in."""
    kept = [item for item in entries if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def movements(records, limit=None):
    """Normalise the records handed in."""
    kept = [item for item in records if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def closing_balance(entries, limit=None):
    """Flatten the entries handed in."""
    kept = [item for item in entries if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
