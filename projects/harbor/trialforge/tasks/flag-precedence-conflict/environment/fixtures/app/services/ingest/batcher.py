"""Inbound batching."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


def chunk(rows):
    limit = flags.get_int("ingest.max_batch_rows", default=1000)
    for start in range(0, len(rows), limit):
        yield rows[start:start + limit]


def load(rows, sink):
    loaded = 0
    for part in chunk(rows):
        loaded += sink.copy(part)
    return loaded
