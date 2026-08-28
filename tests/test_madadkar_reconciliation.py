"""Madadkar Apex C1 payment reconciliation tests."""

from __future__ import annotations

import pytest

from apps.madadkar.choices import PaymentStatus, ReconciliationItemStatus, ReconciliationStatus
from apps.madadkar.models import Payment, PaymentReconciliationBatch
from apps.madadkar.services import reconcile_provider_payments
from tests.factories import UserFactory
from tests.factories.madadkar import PaidParticipationFactory, PaymentFactory

pytestmark = pytest.mark.django_db


def _success_payment(
    *, authority: str = "AUTH-1", ref_id: str = "REF-1", amount: int = 100_000
) -> Payment:
    """Create a successful internal payment."""
    participation = PaidParticipationFactory(total_amount=amount)
    return PaymentFactory(
        participation=participation,
        user=participation.user,
        amount=amount,
        gateway_name="sandbox",
        authority=authority,
        ref_id=ref_id,
        status=PaymentStatus.SUCCESS,
    )


def test_reconciliation_classifies_matched_row() -> None:
    """Provider row matching internal payment should be MATCHED."""
    payment = _success_payment(authority="A1", ref_id="R1", amount=50_000)

    batch = reconcile_provider_payments(
        provider_name="sandbox",
        rows=[{"authority": "A1", "ref_id": "R1", "amount": 50_000, "status": "success"}],
        source_name="settlement.csv",
    )
    item = batch.items.get()

    assert batch.status == ReconciliationStatus.COMPLETED
    assert batch.total_rows == 1
    assert batch.matched_count == 1
    assert batch.mismatch_count == 0
    assert item.payment == payment
    assert item.status == ReconciliationItemStatus.MATCHED


def test_reconciliation_detects_missing_internal_payment() -> None:
    """Provider row without internal payment should be missing_internal."""
    batch = reconcile_provider_payments(
        provider_name="sandbox",
        rows=[
            {"authority": "UNKNOWN", "ref_id": "REF-MISSING", "amount": 10_000, "status": "success"}
        ],
    )
    item = batch.items.get()

    assert batch.missing_internal_count == 1
    assert item.status == ReconciliationItemStatus.MISSING_INTERNAL
    assert item.payment is None


def test_reconciliation_detects_amount_and_status_mismatches() -> None:
    """Amount and status mismatches must be classified separately."""
    _success_payment(authority="A2", ref_id="R2", amount=100_000)
    pending = PaymentFactory(
        participation=PaidParticipationFactory(total_amount=20_000),
        user=UserFactory(),
        amount=20_000,
        gateway_name="sandbox",
        authority="A3",
        ref_id="R3",
        status=PaymentStatus.PENDING,
    )

    batch = reconcile_provider_payments(
        provider_name="sandbox",
        rows=[
            {"authority": "A2", "ref_id": "R2", "amount": 90_000, "status": "success"},
            {"authority": "A3", "ref_id": "R3", "amount": 20_000, "status": "success"},
        ],
    )
    statuses = set(batch.items.values_list("status", flat=True))

    assert pending.status == PaymentStatus.PENDING
    assert ReconciliationItemStatus.AMOUNT_MISMATCH in statuses
    assert ReconciliationItemStatus.STATUS_MISMATCH in statuses
    assert batch.mismatch_count == 2


def test_reconciliation_detects_duplicate_provider_ref() -> None:
    """Duplicate ref_id in provider report should be detected."""
    _success_payment(authority="A4", ref_id="R4", amount=10_000)

    batch = reconcile_provider_payments(
        provider_name="sandbox",
        rows=[
            {"authority": "A4", "ref_id": "R4", "amount": 10_000, "status": "success"},
            {"authority": "A4", "ref_id": "R4", "amount": 10_000, "status": "success"},
        ],
    )

    assert batch.duplicate_provider_ref_count == 1
    assert batch.items.filter(status=ReconciliationItemStatus.DUPLICATE_PROVIDER_REF).exists()


def test_reconciliation_batch_summary_is_auditable() -> None:
    """Batch summary should persist aggregate reconciliation counters."""
    _success_payment(authority="A5", ref_id="R5", amount=10_000)
    batch = reconcile_provider_payments(
        provider_name="sandbox",
        rows=[{"authority": "A5", "ref_id": "R5", "amount": 10_000, "status": "success"}],
    )

    persisted = PaymentReconciliationBatch.objects.get(pk=batch.pk)
    assert persisted.summary == {
        "matched": 1,
        "mismatches": 0,
        "missing_internal": 0,
        "duplicate_provider_ref": 0,
    }
    assert persisted.completed_at is not None
