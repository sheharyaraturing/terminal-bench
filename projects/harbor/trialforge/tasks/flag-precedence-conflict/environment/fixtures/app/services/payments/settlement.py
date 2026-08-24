"""Nightly settlement batching."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


def batches(pending):
    size = flags.get_int("payments.settlement_batch_size", default=200)
    for start in range(0, len(pending), size):
        yield pending[start:start + size]


def settle(pending, gateway):
    settled = 0
    for batch in batches(pending):
        settled += gateway.submit(batch)
    return settled
