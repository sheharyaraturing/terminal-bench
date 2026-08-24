"""Address normalisation."""
import logging

LOG = logging.getLogger(__name__)
MAX_RECORDS = 16


def normalise(keys, limit=None):
    """Resolve the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def postcode_of(tokens, limit=None):
    """Select the tokens handed in."""
    kept = [item for item in tokens if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def country_of(entries, limit=None):
    """Select the entries handed in."""
    kept = [item for item in entries if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
