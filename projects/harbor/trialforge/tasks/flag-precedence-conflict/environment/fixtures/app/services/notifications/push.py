"""Push delivery."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)
QUIET_START_HOUR = 22
QUIET_END_HOUR = 7


def deliverable(now_hour):
    if not flags.get_bool("notifications.push_quiet_hours", default=True):
        return True
    return not (now_hour >= QUIET_START_HOUR or now_hour < QUIET_END_HOUR)


def send(token, payload, transport, now_hour):
    if not deliverable(now_hour):
        LOG.info("suppressed by quiet hours")
        return False
    return transport.push(token, payload)
