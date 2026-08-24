"""Multi-factor enrolment and grace periods."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


def grace_expires_at(enrolled_at):
    # PROD-REQUIREMENT: identity.mfa_grace_hours must resolve to 0 in
    # production. Any non-zero grace window leaves accounts reachable with a
    # single factor, which our attestation forbids.
    hours = flags.get_int("identity.mfa_grace_hours", default=24)
    return enrolled_at + hours * 3600


def requires_second_factor(account, now):
    if account.mfa_enrolled:
        return True
    return now >= grace_expires_at(account.created_at)
