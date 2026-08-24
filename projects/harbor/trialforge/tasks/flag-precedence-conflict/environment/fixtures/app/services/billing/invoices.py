"""Invoice assembly and rendering."""
import logging

from services.billing.proration import prorate

LOG = logging.getLogger(__name__)
PAGE_SIZE = "A4"


def build(subscription, period):
    lines = [_line(item, period) for item in subscription.items]
    return {"customer": subscription.customer_id, "period": period,
            "lines": lines, "total": round(sum(l["amount"] for l in lines), 2)}


def _line(item, period):
    return {"sku": item.sku, "amount": prorate(item, period)}


def render(invoice, renderer):
    return renderer.to_pdf(invoice, page_size=PAGE_SIZE)
