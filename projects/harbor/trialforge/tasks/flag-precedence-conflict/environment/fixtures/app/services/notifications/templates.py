"""Notification body templates."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


def render(kind, context):
    body = _BODIES[kind].format(**context)
    if flags.get_bool("notifications.push_quiet_hours", default=True):
        body = body.rstrip()
    return body


_BODIES = {
    "receipt": "Thanks - your order {order_ref} is confirmed.",
    "shipped": "Order {order_ref} is on its way.",
    "failed": "We could not take payment for {order_ref}.",
}
