"""Express-lane gating."""
from platform import flags
from services.checkout import express


def test_express_off_by_default(monkeypatch, basket, customer):
    monkeypatch.setattr(flags, "enabled", lambda name, fallback=False: False)
    assert express.express_available(basket, customer) is False


def test_express_on(monkeypatch, basket, customer):
    monkeypatch.setattr(
        flags, "enabled",
        lambda name, fallback=False: name == "checkout.express_lane")
    assert express.express_available(basket, customer) is True
