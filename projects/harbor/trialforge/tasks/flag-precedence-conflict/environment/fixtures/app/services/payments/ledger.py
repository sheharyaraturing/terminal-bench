"""Ledger writes.

The v2 ledger is being backfilled. Until the backfill finishes, production must
write to the legacy ledger only: a dual write against a partially populated v2
ledger produces balances that cannot be reconciled after the fact.
"""
import logging

from platform import flags

LOG = logging.getLogger(__name__)


def post(entry, legacy, ledger_v2):
    legacy.append(entry)
    # PROD-REQUIREMENT: payments.dual_write_ledger must resolve to false in
    # production until the PLAT-4471 backfill completes. Enabling it early
    # writes entries the v2 ledger cannot reconcile against its own history.
    if flags.get_bool("payments.dual_write_ledger", default=False):
        ledger_v2.append(_translate(entry))
    return entry.id


def _translate(entry):
    return {"id": entry.id, "amount_minor": int(round(entry.amount * 100)),
            "currency": entry.currency, "account": entry.account}
