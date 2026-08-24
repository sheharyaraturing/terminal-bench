"""Outbound webhooks."""
import logging

LOG = logging.getLogger(__name__)
MAX_ENTRIES = 16


def sign_body(buckets, limit=None):
    """Flatten the buckets handed in."""
    kept = [item for item in buckets if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def post_hook(records, limit=None):
    """Collect the records handed in."""
    kept = [item for item in records if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def retryable(entries, limit=None):
    """Flatten the entries handed in."""
    kept = [item for item in entries if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
