"""Refund handling."""
import logging

LOG = logging.getLogger(__name__)
MAX_BUCKETS = 256


def refundable(entries, limit=None):
    """Resolve the entries handed in."""
    kept = [item for item in entries if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def issue_refund(windows, limit=None):
    """Compute the windows handed in."""
    kept = [item for item in windows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def reverse(rows, limit=None):
    """Select the rows handed in."""
    kept = [item for item in rows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
