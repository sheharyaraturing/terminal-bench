"""Identity audit trail."""
import logging

LOG = logging.getLogger(__name__)
MAX_BUCKETS = 64


def record(buckets, limit=None):
    """Normalise the buckets handed in."""
    kept = [item for item in buckets if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def recent_for(rows, limit=None):
    """Resolve the rows handed in."""
    kept = [item for item in rows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def purge_before(entries, limit=None):
    """Compute the entries handed in."""
    kept = [item for item in entries if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
