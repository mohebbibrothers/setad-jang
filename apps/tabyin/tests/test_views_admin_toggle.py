"""
Tests — apps.tabyin.views.AdminTabyinContentToggleView (API layer)

این تست‌ها endpoint زیر را end-to-end verify می‌کنند:
    PATCH /api/v1/tabyin/admin/contents/{external_id}/toggle/

سناریوهای پوشش‌داده‌شده:
- ادمین می‌تواند یک محتوا را فعال/غیرفعال کند و response envelope
  استاندارد پروژه را دریافت کند.
- یک کاربر عادی نباید بتواند به این endpoint دسترسی داشته باشد.
- درخواست بدون احراز هویت باید رد شود.
- اگر external_id ناموجود باشد، 404 با envelope صحیح برگردد.

اصول طراحی:
- تست‌ها contract لایه‌ی API را verify می‌کنند، نه implementation داخلی view.
- داده فقط از طریق factory-boy ساخته می‌شود.
- response envelope پروژه (success/status_code/message/data) نیز verify می‌شود.
- هیچ تغییری در کد production لازم نیست.
- pytestmark = django_db تضمین می‌کند هر تستی در این فایل اجازه‌ی دسترسی
  به DB را داشته باشد، چون از factory-boy برای ساخت داده استفاده می‌کنیم.
"""

from __future__ import annotations

import pytest
from rest_framework import status

from tests.factories import TabyinContentFactory

pytestmark = [pytest.mark.django_db]


def _toggle_url(external_id: str) -> str:
    return f"/api/v1/tabyin/admin/contents/{external_id}/toggle/"


# ============================================================
# Permission boundaries
# ============================================================


class TestAdminToggleViewPermissions:
    """دسترسی به endpoint فقط برای ادمین مجاز است."""

    def test_unauthenticated_request_is_rejected(self, api_client) -> None:
        content = TabyinContentFactory(is_active=True)

        response = api_client.patch(
            _toggle_url(content.external_id),
            data={"is_active": False},
            format="json",
        )

        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }

    def test_regular_user_cannot_access(self, authenticated_client) -> None:
        content = TabyinContentFactory(is_active=True)

        response = authenticated_client.patch(
            _toggle_url(content.external_id),
            data={"is_active": False},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================
# Happy path
# ============================================================


class TestAdminToggleViewSuccess:
    """رفتار موفق ادمین در toggle کردن محتوا."""

    def test_admin_can_deactivate_active_content(self, admin_client) -> None:
        content = TabyinContentFactory(is_active=True, is_deleted_in_source=False)

        response = admin_client.patch(
            _toggle_url(content.external_id),
            data={"is_active": False},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        assert body["success"] is True
        assert body["status_code"] == 200
        assert isinstance(body.get("message"), str)
        assert "data" in body

        data = body["data"]
        assert data["external_id"] == content.external_id
        assert data["is_active"] is False

        content.refresh_from_db()
        assert content.is_active is False

    def test_admin_can_activate_inactive_content(self, admin_client) -> None:
        content = TabyinContentFactory(is_active=False, is_deleted_in_source=False)

        response = admin_client.patch(
            _toggle_url(content.external_id),
            data={"is_active": True},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        assert body["success"] is True
        assert body["data"]["is_active"] is True

        content.refresh_from_db()
        assert content.is_active is True


# ============================================================
# Not found
# ============================================================


class TestAdminToggleViewNotFound:
    """external_id ناموجود باید 404 با envelope استاندارد بدهد."""

    def test_returns_404_for_unknown_external_id(self, admin_client) -> None:
        response = admin_client.patch(
            _toggle_url("does-not-exist-id"),
            data={"is_active": True},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        body = response.json()
        assert body["success"] is False
        assert body["status_code"] == 404
        assert isinstance(body.get("message"), str)
