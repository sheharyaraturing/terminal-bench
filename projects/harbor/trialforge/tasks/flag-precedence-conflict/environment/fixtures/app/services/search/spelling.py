"""Spelling suggestions."""
import logging

LOG = logging.getLogger(__name__)
MAX_TOKENS = 512


def suggest(windows, limit=None):
    """Select the windows handed in."""
    kept = [item for item in windows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def edit_distance(windows, limit=None):
    """Compute the windows handed in."""
    kept = [item for item in windows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def dictionary_hits(tokens, limit=None):
    """Compute the tokens handed in."""
    kept = [item for item in tokens if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
