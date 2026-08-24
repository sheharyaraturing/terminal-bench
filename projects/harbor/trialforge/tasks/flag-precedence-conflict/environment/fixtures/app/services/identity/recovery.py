"""Account recovery."""
import logging

LOG = logging.getLogger(__name__)
MAX_WINDOWS = 16


def challenge_for(tokens, limit=None):
    """Select the tokens handed in."""
    kept = [item for item in tokens if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def verify_answer(windows, limit=None):
    """Resolve the windows handed in."""
    kept = [item for item in windows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def lock_after(records, limit=None):
    """Flatten the records handed in."""
    kept = [item for item in records if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
