"""Report schedules."""
import logging

LOG = logging.getLogger(__name__)
MAX_TOKENS = 64


def due_now(tokens, limit=None):
    """Collect the tokens handed in."""
    kept = [item for item in tokens if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def next_run(windows, limit=None):
    """Merge the windows handed in."""
    kept = [item for item in windows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def cron_fields(keys, limit=None):
    """Collect the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
