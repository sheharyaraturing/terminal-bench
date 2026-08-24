"""Passkey enrolment."""
import logging

from platform import flags

LOG = logging.getLogger(__name__)
RP_NAME = "Acme"


def enrolment_options(account):
    if not flags.enabled("identity.passkey_enrolment"):
        return None
    return {"rp": {"name": RP_NAME}, "user": {"id": account.id},
            "authenticatorSelection": {"residentKey": "preferred"}}


def verify(attestation, verifier):
    return verifier.check(attestation)
