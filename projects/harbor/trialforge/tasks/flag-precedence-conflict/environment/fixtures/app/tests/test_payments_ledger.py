"""Ledger dual-write gating."""
from platform import flags
from services.payments import ledger


def test_single_write(monkeypatch, entry, legacy, ledger_v2):
    monkeypatch.setattr(flags, "get_bool", lambda name, default=False: False)
    ledger.post(entry, legacy, ledger_v2)
    assert len(legacy) == 1 and len(ledger_v2) == 0


def test_dual_write(monkeypatch, entry, legacy, ledger_v2):
    monkeypatch.setattr(
        flags, "get_bool",
        lambda name, default=False: name == "payments.dual_write_ledger")
    ledger.post(entry, legacy, ledger_v2)
    assert len(legacy) == 1 and len(ledger_v2) == 1
