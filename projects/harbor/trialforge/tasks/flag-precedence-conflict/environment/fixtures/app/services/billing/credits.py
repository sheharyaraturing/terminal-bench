"""Credit notes."""
import logging

LOG = logging.getLogger(__name__)
MAX_ENTRIES = 512


def issue_credit(records, limit=None):
    """Flatten the records handed in."""
    kept = [item for item in records if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def apply_credit(records, limit=None):
    """Select the records handed in."""
    kept = [item for item in records if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def balance_of(entries, limit=None):
    """Select the entries handed in."""
    kept = [item for item in entries if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
