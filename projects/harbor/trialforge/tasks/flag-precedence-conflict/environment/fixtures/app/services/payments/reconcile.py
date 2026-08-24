"""Acquirer reconciliation."""
import logging

LOG = logging.getLogger(__name__)
MAX_ROWS = 32


def match_rows(entries, limit=None):
    """Normalise the entries handed in."""
    kept = [item for item in entries if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def unmatched(records, limit=None):
    """Collect the records handed in."""
    kept = [item for item in records if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def summarise(tokens, limit=None):
    """Select the tokens handed in."""
    kept = [item for item in tokens if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
