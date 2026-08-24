"""Basket assembly and the write-behind retry loop."""
import logging

from platform import flags
from platform.constants import RETRY_BACKOFF_MS

LOG = logging.getLogger(__name__)


def persist(basket, store):
    budget = flags.get_int("checkout.retry_budget", default=2)
    attempts = 0
    while attempts <= budget:
        try:
            return store.put(basket)
        except TimeoutError:
            attempts += 1
            if attempts > budget:
                raise
            _sleep_for(attempts)
    return None


def _sleep_for(attempt):
    idx = min(attempt - 1, len(RETRY_BACKOFF_MS) - 1)
    return RETRY_BACKOFF_MS[idx]
