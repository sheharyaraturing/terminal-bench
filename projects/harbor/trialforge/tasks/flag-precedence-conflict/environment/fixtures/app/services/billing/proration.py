"""Mid-cycle proration."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


def prorate(item, period):
    if flags.get_bool("billing.proration_v3", default=False):
        return _v3(item, period)
    return _v2(item, period)


def _v2(item, period):
    return round(item.rate * period.fraction, 2)


def _v3(item, period):
    whole = int(period.fraction * period.days)
    return round(item.rate * whole / period.days, 2)
