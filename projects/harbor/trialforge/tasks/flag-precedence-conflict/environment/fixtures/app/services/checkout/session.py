"""Checkout session lifecycle."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)
SESSION_TTL_S = 1800


def resume(session_id, store):
    budget = flags.get_int("checkout.retry_budget", default=2)
    for _ in range(budget + 1):
        session = store.load(session_id)
        if session is not None:
            return session
    LOG.info("session could not be resumed")
    return None


def expire_stale(store, now):
    return store.purge_older_than(now - SESSION_TTL_S)
