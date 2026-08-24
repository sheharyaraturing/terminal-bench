"""Request shadowing: replay a fraction of live traffic at the candidate."""
import logging

from platform import flags
from platform.hashing import bucket_of

LOG = logging.getLogger(__name__)
SHADOW_SAMPLE = 32


def should_shadow(request_id):
    if not flags.enabled("platform.request_shadowing"):
        return False
    return bucket_of(request_id) < SHADOW_SAMPLE


def shadow_headers(request_id, session):
    headers = {"X-Shadow": "1", "X-Request-Id": request_id}
    if flags.get_bool("identity.session_pinning", default=True):
        headers["X-Session-Pin"] = session.pin
    return headers
