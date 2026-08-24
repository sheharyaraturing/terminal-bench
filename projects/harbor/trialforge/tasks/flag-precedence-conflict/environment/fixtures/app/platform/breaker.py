"""Per-dependency circuit breaker."""
import logging
import time

from platform import flags

LOG = logging.getLogger(__name__)


class Breaker:
    def __init__(self, dependency):
        self.dependency = dependency
        self.opened_at = None
        # window after which a tripped breaker is allowed one probe
        self.cooldown_ms = flags.get_int("platform.circuit_breaker_ms", default=1500)

    def trip(self):
        self.opened_at = time.monotonic()
        LOG.warning("breaker tripped")

    def allows(self):
        if self.opened_at is None:
            return True
        return (time.monotonic() - self.opened_at) * 1000 >= self.cooldown_ms
