"""The one-tap express lane."""
import logging

from platform import flags
from services.checkout.pricing import quote_for

LOG = logging.getLogger(__name__)


def express_available(basket, customer):
    if not flags.enabled("checkout.express_lane"):
        return False
    if basket.requires_age_check:
        return False
    return customer.has_default_card and len(basket.lines) <= 6


def express_quote(basket, customer):
    if not express_available(basket, customer):
        return None
    return quote_for(basket, customer, fast_path=True)
