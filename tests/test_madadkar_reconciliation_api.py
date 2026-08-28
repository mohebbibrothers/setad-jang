"""Madadkar C6 settlement import/reconciliation API tests."""

from __future__ import annotations

from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.models import AuditLog
from apps.madadkar.choices import PaymentStatus, ReconciliationItemStatus
from apps.madadkar.models import PaymentReconciliationBatch
from apps.madadkar.reconciliation import parse_settlement_report
from tests.factories.auth import AdminUserFactory
from tests.factories.madadkar import PaidParticipationFactory, PaymentFactory

pytestmark = pytest.mark.django_db


def _admin_client(admin_user=None) -> APIClient:
    """Build JWT-authenticated admin client."""
    user = admin_user or AdminUserFactory()
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


def _success_payment(
    *, authority: str = "AUTH-C6-1", ref_id: str = "REF-C6-1", amount: int = 50_000
):
    """Create a successful internal sandbox payment for reconciliation."""
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


def _csv_upload(content: str, name: str = "settlement.csv") -> SimpleUploadedFile:
    """Build CSV upload file for reconciliation import endpoint."""
    return SimpleUploadedFile(name, content.encode("utf-8-sig"), content_type="text/csv")


def _xlsx_bytes() -> bytes:
    """Build XLSX settlement file bytes."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["authority", "ref_id", "amount", "status"])
    sheet.append(["AUTH-XLSX", "REF-XLSX", 12_000, "success"])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_parse_settlement_report_supports_xlsx() -> None:
    """Parser should normalize XLSX rows into canonical reconciliation rows."""
    rows = parse_settlement_report(filename="settlement.xlsx", content=_xlsx_bytes())

    assert rows == [
        {
            "authority": "AUTH-XLSX",
            "ref_id": "REF-XLSX",
            "amount": 12_000,
            "status": "success",
            "raw_payload": {
                "authority": "AUTH-XLSX",
                "ref_id": "REF-XLSX",
                "amount": 12_000,
                "status": "success",
            },
        }
    ]


def test_admin_reconciliation_import_csv_creates_batch_items_and_audit() -> None:
    """Admin CSV import should reconcile rows and audit the import."""
    _success_payment(authority="AUTH-C6-1", ref_id="REF-C6-1", amount=50_000)
    csv_file = _csv_upload(
        "authority,ref_id,amount,status\n"
        "AUTH-C6-1,REF-C6-1,50000,success\n"
        "UNKNOWN,REF-MISSING,10000,success\n"
    )
    client = _admin_client()

    response = client.post(
        reverse("madadkar:admin-reconciliation-import"),
        data={"provider_name": "sandbox", "source_name": "daily-settlement.csv", "file": csv_file},
        format="multipart",
    )

    assert response.status_code == status.HTTP_201_CREATED
    batch = PaymentReconciliationBatch.objects.get(pk=response.data["data"]["id"])
    assert batch.total_rows == 2
    assert batch.matched_count == 1
    assert batch.missing_internal_count == 1
    assert batch.items.filter(status=ReconciliationItemStatus.MATCHED).exists()
    assert batch.items.filter(status=ReconciliationItemStatus.MISSING_INTERNAL).exists()
    assert AuditLog.objects.filter(
        action=audit_actions.MADADKAR_RECONCILIATION_IMPORTED,
        resource_id=str(batch.pk),
    ).exists()


def test_admin_reconciliation_endpoints_list_detail_items_and_export() -> None:
    """Admin review endpoints should expose batches/items and discrepancy CSV export."""
    _success_payment(authority="AUTH-C6-2", ref_id="REF-C6-2", amount=50_000)
    client = _admin_client()
    import_response = client.post(
        reverse("madadkar:admin-reconciliation-import"),
        data={
            "provider_name": "sandbox",
            "file": _csv_upload(
                "authority,ref_id,amount,status\n"
                "AUTH-C6-2,REF-C6-2,40000,success\n"
                "AUTH-C6-2,REF-C6-2,50000,success\n",
            ),
        },
        format="multipart",
    )
    batch_id = import_response.data["data"]["id"]

    list_response = client.get(reverse("madadkar:admin-reconciliation-batch-list"))
    detail_response = client.get(
        reverse("madadkar:admin-reconciliation-batch-detail", kwargs={"batch_id": batch_id})
    )
    items_response = client.get(
        reverse("madadkar:admin-reconciliation-item-list", kwargs={"batch_id": batch_id})
    )
    export_response = client.get(
        reverse("madadkar:admin-reconciliation-discrepancy-export", kwargs={"batch_id": batch_id})
    )

    assert list_response.status_code == status.HTTP_200_OK
    assert detail_response.status_code == status.HTTP_200_OK
    assert items_response.status_code == status.HTTP_200_OK
    assert items_response.data["data"]["count"] == 2
    assert export_response.status_code == status.HTTP_200_OK
    assert export_response["Content-Type"].startswith("text/csv")
    assert b"amount_mismatch" in export_response.content
    assert AuditLog.objects.filter(
        action=audit_actions.MADADKAR_RECONCILIATION_EXPORTED,
        resource_id=str(batch_id),
    ).exists()


def test_admin_reconciliation_import_rejects_malformed_file() -> None:
    """Malformed provider settlement files should fail loudly with 400."""
    client = _admin_client()

    response = client.post(
        reverse("madadkar:admin-reconciliation-import"),
        data={"provider_name": "sandbox", "file": _csv_upload("authority,amount\nAUTH,1000\n")},
        format="multipart",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["success"] is False
