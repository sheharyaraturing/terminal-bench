"""Dunning schedule."""
from services.billing import dunning


def test_schedule_walks_forward():
    assert [dunning.next_attempt(i) for i in range(5)] == [1, 3, 7, 14, 21]


def test_schedule_exhausts():
    assert dunning.next_attempt(5) is None
    assert dunning.should_suspend(6) is True


def test_removed_pdf_gate_is_not_reintroduced():
    retired_gate = "billing.legacy_invoice_pdf"
    assert retired_gate not in dunning.__dict__
