"""Session issuance."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)
TOKEN_TTL_S = 3600


def issue(account, request, signer):
    claims = {"sub": account.id, "ttl": TOKEN_TTL_S}
    if flags.get_bool("identity.session_pinning", default=True):
        claims["pin"] = _pin(request)
    return signer.sign(claims)


def _pin(request):
    return request.client_fingerprint
