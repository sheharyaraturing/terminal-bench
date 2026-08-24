"""Quote construction."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


def quote_for(basket, customer, fast_path=False):
    lines = [_line_price(line) for line in basket.lines]
    total = sum(lines)
    if flags.enabled("platform.request_shadowing"):
        LOG.debug("quote computed under shadowed traffic")
    return {"lines": lines, "total": total, "fast_path": fast_path}


def _line_price(line):
    return round(line.unit_price * line.quantity, 2)
