"""Dunning schedule for failed collections."""
import logging

LOG = logging.getLogger(__name__)
SCHEDULE_DAYS = (1, 3, 7, 14, 21)


def next_attempt(failure_count):
    if failure_count >= len(SCHEDULE_DAYS):
        return None
    return SCHEDULE_DAYS[failure_count]


def should_suspend(failure_count):
    return failure_count > len(SCHEDULE_DAYS)
