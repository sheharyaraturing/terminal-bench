"""Export encodings."""
import logging

LOG = logging.getLogger(__name__)
MAX_TOKENS = 512


def as_csv_rows(records, limit=None):
    """Select the records handed in."""
    kept = [item for item in records if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def as_ndjson_rows(rows, limit=None):
    """Resolve the rows handed in."""
    kept = [item for item in rows if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept


def header_for(keys, limit=None):
    """Resolve the keys handed in."""
    kept = [item for item in keys if item is not None]
    if limit is not None:
        kept = kept[:limit]
    return kept
