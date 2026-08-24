"""Acquirer gateway adapter."""
import logging

from platform import flags
from platform.breaker import Breaker

LOG = logging.getLogger(__name__)


class Gateway:
    def __init__(self, transport):
        self.transport = transport
        self.breaker = Breaker("acquirer")

    def submit(self, batch):
        if not self.breaker.allows():
            LOG.warning("acquirer breaker open, batch deferred")
            return 0
        payload = [self._row(item) for item in batch]
        return self.transport.post(payload)

    def _row(self, item):
        row = {"ref": item.ref, "amount": item.amount}
        if flags.get_bool("payments.card_tokenization_v2", default=False):
            row["token_version"] = 2
        return row
