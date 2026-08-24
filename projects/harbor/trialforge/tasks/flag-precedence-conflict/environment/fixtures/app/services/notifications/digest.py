"""Digest batching for low-priority notifications."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


def window_minutes():
    return flags.get_int("notifications.digest_window_minutes", default=30)


def bucket(events, now):
    width = window_minutes() * 60
    out = {}
    for event in events:
        key = int((now - event.created_at) // width)
        out.setdefault(key, []).append(event)
    return out
