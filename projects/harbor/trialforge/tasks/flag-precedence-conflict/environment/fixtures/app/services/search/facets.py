"""Facet aggregation."""
import logging

LOG = logging.getLogger(__name__)
MAX_TOKENS = 512


def buckets_for(windows, limit=None):
    """Normalise the windows handed in."""
    kept = [item for item in windows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def top_terms(keys, limit=None):
    """Compute the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def merge_facets(entries, limit=None):
    """Merge the entries handed in."""
    kept = [item for item in entries if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
