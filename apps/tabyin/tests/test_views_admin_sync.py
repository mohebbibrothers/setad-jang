"""
Tests — apps.tabyin.views (Admin async sync endpoints, API layer)

این تست‌ها دو endpoint زیر را end-to-end verify می‌کنند:
- POST /api/v1/tabyin/admin/sync/                       (dispatch)
- GET  /api/v1/tabyin/admin/sync/status/{task_id}/      (status)

اصول طراحی:
- mocking در مرز view→service انجام می‌شود (apps.tabyin.views.services).
  این یعنی هیچ Celery worker، هیچ broker و هیچ sync engine واقعی اجرا نمی‌شود.
- response envelope استاندارد پروژه (success/status_code/message/data) verify می‌شود.
- permission boundaries و contract لایه‌ی API هر دو پوشش داده می‌شوند.
- metadata مربوط به trigger انسانی (user_id / request_id / dispatch_ip)
  به service layer propagate می‌شود.
- assertها روی datetime به‌صورت semantic انجام می‌شوند، نه string، چون
  DRF DateTimeField خروجی را طبق TIME_ZONE پروژه (Asia/Tehran) localize می‌کند.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from rest_framework import status

pytestmark = [pytest.mark.django_db]


_DISPATCH_URL = "/api/v1/tabyin/admin/sync/"


def _status_url(task_id: str) -> str:
    return f"/api/v1/tabyin/admin/sync/status/{task_id}/"


# ============================================================
# Permission boundaries — dispatch
# ============================================================


class TestAdminSyncDispatchPermissions:
    """دسترسی به dispatch endpoint فقط برای ادمین مجاز است."""

    def test_unauthenticated_request_is_rejected(self, api_client) -> None:
        response = api_client.post(
            _DISPATCH_URL,
            data={"mode": "incremental"},
            format="json",
        )

        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }

    def test_regular_user_cannot_access(self, authenticated_client) -> None:
        response = authenticated_client.post(
            _DISPATCH_URL,
            data={"mode": "incremental"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================
# Happy path — dispatch
# ============================================================


class TestAdminSyncDispatchSuccess:
    """رفتار موفق ادمین در صدور درخواست async sync."""

    def test_admin_dispatch_returns_202_with_envelope_and_task_id(
        self,
        admin_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured_payload: dict[str, Any] = {}

        def fake_dispatch(
            *,
            mode: str,
            triggered_by_user_id: int | None,
            request_id: str | None,
            dispatch_ip: str | None,
        ) -> str:
            captured_payload["mode"] = mode
            captured_payload["triggered_by_user_id"] = triggered_by_user_id
            captured_payload["request_id"] = request_id
            captured_payload["dispatch_ip"] = dispatch_ip
            return "fake-task-id-001"

        monkeypatch.setattr(
            "apps.tabyin.views.services.dispatch_sync_task",
            fake_dispatch,
        )

        response = admin_client.post(
            _DISPATCH_URL,
            data={"mode": "incremental"},
            format="json",
            HTTP_X_REQUEST_ID="sync-req-001",
        )

        assert response.status_code == status.HTTP_202_ACCEPTED

        body = response.json()
        assert body["success"] is True
        assert body["status_code"] == 202
        assert isinstance(body.get("message"), str)

        data = body["data"]
        assert data["task_id"] == "fake-task-id-001"
        assert data["mode"] == "incremental"
        assert isinstance(data["status_url"], str)
        assert "fake-task-id-001" in data["status_url"]

        assert captured_payload["mode"] == "incremental"
        assert isinstance(captured_payload["triggered_by_user_id"], int)
        assert captured_payload["triggered_by_user_id"] > 0
        assert captured_payload["request_id"] == "sync-req-001"
        assert captured_payload["dispatch_ip"] is not None

    def test_admin_dispatch_full_mode_uses_full_task(
        self,
        admin_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured_modes: list[str] = []

        def fake_dispatch(
            *,
            mode: str,
            triggered_by_user_id: int | None,
            request_id: str | None,
            dispatch_ip: str | None,
        ) -> str:
            captured_modes.append(mode)
            return "fake-task-id-002"

        monkeypatch.setattr(
            "apps.tabyin.views.services.dispatch_sync_task",
            fake_dispatch,
        )

        response = admin_client.post(
            _DISPATCH_URL,
            data={"mode": "full"},
            format="json",
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.json()["data"]["mode"] == "full"
        assert captured_modes == ["full"]


# ============================================================
# Permission boundaries — status
# ============================================================


class TestAdminSyncStatusPermissions:
    """دسترسی به status endpoint فقط برای ادمین مجاز است."""

    def test_unauthenticated_request_is_rejected(self, api_client) -> None:
        response = api_client.get(_status_url("any-task-id"))
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }

    def test_regular_user_cannot_access(self, authenticated_client) -> None:
        response = authenticated_client.get(_status_url("any-task-id"))
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================
# Happy path — status (success)
# ============================================================


class TestAdminSyncStatusSuccessPath:
    """contract سرویس status برای task موفق."""

    def test_returns_success_payload_with_envelope(
        self,
        admin_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        expected_started_at = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

        fake_payload: dict[str, Any] = {
            "task_id": "fake-task-id-success",
            "state": "SUCCESS",
            "ready": True,
            "successful": True,
            "result": {
                "pages_fetched": 1,
                "items_processed": 30,
                "created": 0,
                "updated": 0,
                "unchanged": 30,
                "soft_deleted": 0,
                "errors": 0,
                "skipped": 0,
                "duration_seconds": 1.23,
                "started_at": expected_started_at.isoformat(),
            },
            "error": None,
        }

        def fake_status(*, task_id: str) -> dict[str, Any]:
            assert task_id == "fake-task-id-success"
            return fake_payload

        monkeypatch.setattr(
            "apps.tabyin.views.services.get_sync_task_status",
            fake_status,
        )

        response = admin_client.get(_status_url("fake-task-id-success"))

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        assert body["success"] is True
        assert body["status_code"] == 200

        data = body["data"]
        assert data["task_id"] == "fake-task-id-success"
        assert data["state"] == "SUCCESS"
        assert data["ready"] is True
        assert data["successful"] is True
        assert data["error"] is None

        result = data["result"]
        assert result["pages_fetched"] == 1
        assert result["unchanged"] == 30
        assert result["duration_seconds"] == 1.23

        # Semantic comparison (در هر تایم‌زون نمایش داده شود، یک لحظه‌ی واحد است)
        assert isinstance(result["started_at"], str)
        actual_started_at = datetime.fromisoformat(result["started_at"])
        assert actual_started_at == expected_started_at


# ============================================================
# Happy path — status (failure)
# ============================================================


class TestAdminSyncStatusFailurePath:
    """contract سرویس status برای task شکست‌خورده."""

    def test_returns_failure_payload_with_envelope(
        self,
        admin_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_payload: dict[str, Any] = {
            "task_id": "fake-task-id-failure",
            "state": "FAILURE",
            "ready": True,
            "successful": False,
            "result": None,
            "error": "RuntimeError: simulated sync failure",
        }

        def fake_status(*, task_id: str) -> dict[str, Any]:
            return fake_payload

        monkeypatch.setattr(
            "apps.tabyin.views.services.get_sync_task_status",
            fake_status,
        )

        response = admin_client.get(_status_url("fake-task-id-failure"))

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        assert body["success"] is True
        assert body["status_code"] == 200

        data = body["data"]
        assert data["task_id"] == "fake-task-id-failure"
        assert data["state"] == "FAILURE"
        assert data["ready"] is True
        assert data["successful"] is False
        assert data["result"] is None
        assert "RuntimeError" in data["error"]
        assert "simulated sync failure" in data["error"]
