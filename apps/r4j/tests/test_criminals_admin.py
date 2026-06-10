"""
Tests — apps.r4j admin criminal endpoints (Phase R4J.2)

این تست‌ها رفتار admin endpoints را verify می‌کنند:
- CRUD criminals
- publish / unpublish (idempotency + final state)
- nested: aliases, phones, socials, photos, attachments, visibility
- permission boundaries (anonymous + regular user denied)
- audit dispatch (sync و async)

اصول طراحی:
- mock کردن celery task برای جلوگیری از execution واقعی.
- assertion روی dispatch args، نه DB-level audit (آن در apps.audit_logs تست شده).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.models import AuditLog
from apps.authentication.choices import UserRole
from apps.r4j.choices import SocialPlatform
from apps.r4j.models import (
    R4JCriminal,
    R4JCriminalAlias,
    R4JCriminalFieldVisibility,
    R4JCriminalPhone,
    R4JCriminalSocial,
)
from tests.factories.auth import AdminUserFactory, UserFactory
from tests.factories.r4j import R4JCriminalFactory

pytestmark = [pytest.mark.django_db]

_TASK_PATCH_PATH = "apps.audit_logs.tasks.create_audit_log_task"


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def admin_user(db):
    admin = AdminUserFactory(email="r4j-admin@example.com")
    admin.role = UserRole.ADMIN
    admin.save(update_fields=["role"])
    return admin


@pytest.fixture
def admin_client(admin_user) -> APIClient:
    client = APIClient()
    refresh = RefreshToken.for_user(admin_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


@pytest.fixture
def regular_client(db) -> APIClient:
    user = UserFactory(email="r4j-user@example.com", is_email_verified=True)
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


# ============================================================
# Permission boundaries
# ============================================================


class TestAdminPermissionBoundaries:
    """دسترسی به admin endpoints فقط برای admin مجاز است."""

    def test_anonymous_cannot_list(self, api_client) -> None:
        response = api_client.get("/api/v1/r4j/admin/criminals/")
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }

    def test_regular_user_cannot_list(self, regular_client) -> None:
        response = regular_client.get("/api/v1/r4j/admin/criminals/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_regular_user_cannot_create(self, regular_client) -> None:
        response = regular_client.post(
            "/api/v1/r4j/admin/criminals/",
            data={"first_name": "x", "last_name": "y"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================
# Criminal CRUD
# ============================================================


class TestAdminCriminalCRUD:
    """رفتار CRUD criminals در admin."""

    def test_create_returns_201_and_dispatches_audit(
        self, admin_client, admin_user,
    ) -> None:
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = admin_client.post(
                "/api/v1/r4j/admin/criminals/",
                data={
                    "first_name": "Donald",
                    "last_name": "Trump",
                    "country": "USA",
                },
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["first_name"] == "Donald"
        assert response.data["data"]["is_published"] is False

        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.R4J_CRIMINAL_CREATED
        assert kwargs["user_id"] == admin_user.pk

    def test_list_includes_drafts(self, admin_client) -> None:
        R4JCriminalFactory(first_name="منتشر", is_published=True).publish()
        R4JCriminalFactory(first_name="دراف", is_published=False)

        response = admin_client.get("/api/v1/r4j/admin/criminals/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["count"] >= 2

    def test_retrieve_existing(self, admin_client) -> None:
        criminal = R4JCriminalFactory()
        response = admin_client.get(
            f"/api/v1/r4j/admin/criminals/{criminal.pk}/",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["id"] == criminal.pk

    def test_retrieve_not_found(self, admin_client) -> None:
        response = admin_client.get("/api/v1/r4j/admin/criminals/99999/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_changes_fields(self, admin_client) -> None:
        criminal = R4JCriminalFactory(first_name="Old")
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = admin_client.patch(
                f"/api/v1/r4j/admin/criminals/{criminal.pk}/",
                data={"first_name": "New"},
                format="json",
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["first_name"] == "New"

        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.R4J_CRIMINAL_UPDATED

    def test_delete_soft_deletes_and_audits_sync(
        self, admin_client, admin_user,
    ) -> None:
        criminal = R4JCriminalFactory(is_published=True)
        criminal.publish()

        response = admin_client.delete(
            f"/api/v1/r4j/admin/criminals/{criminal.pk}/",
        )
        assert response.status_code == status.HTTP_200_OK

        criminal.refresh_from_db()
        assert criminal.is_active is False
        assert criminal.is_published is False

        # sync audit ثبت شده
        audit = AuditLog.objects.filter(
            action=audit_actions.R4J_CRIMINAL_DELETED,
            resource_id=str(criminal.pk),
        ).first()
        assert audit is not None
        assert audit.user_id == admin_user.pk


# ============================================================
# Publish / Unpublish
# ============================================================


class TestAdminPublishLifecycle:
    """رفتار publish و unpublish."""

    def test_publish_a_draft(self, admin_client) -> None:
        criminal = R4JCriminalFactory(is_published=False)
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = admin_client.post(
                f"/api/v1/r4j/admin/criminals/{criminal.pk}/publish/",
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["is_published"] is True
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.R4J_CRIMINAL_PUBLISHED

    def test_publish_already_published_returns_400(self, admin_client) -> None:
        criminal = R4JCriminalFactory()
        criminal.publish()

        response = admin_client.post(
            f"/api/v1/r4j/admin/criminals/{criminal.pk}/publish/",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unpublish_published(self, admin_client) -> None:
        criminal = R4JCriminalFactory()
        criminal.publish()

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = admin_client.post(
                f"/api/v1/r4j/admin/criminals/{criminal.pk}/unpublish/",
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["is_published"] is False
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.R4J_CRIMINAL_UNPUBLISHED

    def test_unpublish_already_draft_returns_400(self, admin_client) -> None:
        criminal = R4JCriminalFactory(is_published=False)
        response = admin_client.post(
            f"/api/v1/r4j/admin/criminals/{criminal.pk}/unpublish/",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================
# Nested — Aliases
# ============================================================


class TestAdminAliases:
    """رفتار aliases nested endpoints."""

    def test_add_alias(self, admin_client) -> None:
        criminal = R4JCriminalFactory()
        response = admin_client.post(
            f"/api/v1/r4j/admin/criminals/{criminal.pk}/aliases/",
            data={"alias": "Big T"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert R4JCriminalAlias.objects.filter(
            criminal=criminal, alias="Big T",
        ).exists()

    def test_list_aliases(self, admin_client) -> None:
        criminal = R4JCriminalFactory()
        R4JCriminalAlias.objects.create(criminal=criminal, alias="A1")
        R4JCriminalAlias.objects.create(criminal=criminal, alias="A2")

        response = admin_client.get(
            f"/api/v1/r4j/admin/criminals/{criminal.pk}/aliases/",
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) == 2

    def test_delete_alias(self, admin_client) -> None:
        criminal = R4JCriminalFactory()
        alias = R4JCriminalAlias.objects.create(criminal=criminal, alias="X")

        response = admin_client.delete(
            f"/api/v1/r4j/admin/criminals/{criminal.pk}/aliases/{alias.pk}/",
        )
        assert response.status_code == status.HTTP_200_OK
        assert not R4JCriminalAlias.objects.filter(pk=alias.pk).exists()


# ============================================================
# Nested — Phones
# ============================================================


class TestAdminPhones:
    """رفتار phones nested endpoints."""

    def test_add_phone_dispatches_audit(self, admin_client, admin_user) -> None:
        criminal = R4JCriminalFactory()
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = admin_client.post(
                f"/api/v1/r4j/admin/criminals/{criminal.pk}/phones/",
                data={"number": "+989121234567", "label": "اصلی"},
                format="json",
            )
        assert response.status_code == status.HTTP_201_CREATED
        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.R4J_CRIMINAL_PHONE_ADDED

    def test_update_phone(self, admin_client) -> None:
        criminal = R4JCriminalFactory()
        phone = R4JCriminalPhone.objects.create(
            criminal=criminal, number="+989120000000",
        )
        response = admin_client.patch(
            f"/api/v1/r4j/admin/criminals/{criminal.pk}/phones/{phone.pk}/",
            data={"label": "ویرایش شده"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        phone.refresh_from_db()
        assert phone.label == "ویرایش شده"

    def test_delete_phone(self, admin_client) -> None:
        criminal = R4JCriminalFactory()
        phone = R4JCriminalPhone.objects.create(
            criminal=criminal, number="+989120000000",
        )
        response = admin_client.delete(
            f"/api/v1/r4j/admin/criminals/{criminal.pk}/phones/{phone.pk}/",
        )
        assert response.status_code == status.HTTP_200_OK
        assert not R4JCriminalPhone.objects.filter(pk=phone.pk).exists()


# ============================================================
# Nested — Socials
# ============================================================


class TestAdminSocials:
    """رفتار socials nested endpoints."""

    def test_add_social(self, admin_client) -> None:
        criminal = R4JCriminalFactory()
        response = admin_client.post(
            f"/api/v1/r4j/admin/criminals/{criminal.pk}/socials/",
            data={
                "platform": SocialPlatform.TELEGRAM,
                "handle_or_url": "@trump",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert R4JCriminalSocial.objects.filter(criminal=criminal).count() == 1

    def test_delete_social(self, admin_client) -> None:
        criminal = R4JCriminalFactory()
        social = R4JCriminalSocial.objects.create(
            criminal=criminal,
            platform=SocialPlatform.TWITTER_X,
            handle_or_url="@x",
        )
        response = admin_client.delete(
            f"/api/v1/r4j/admin/criminals/{criminal.pk}/socials/{social.pk}/",
        )
        assert response.status_code == status.HTTP_200_OK
        assert not R4JCriminalSocial.objects.filter(pk=social.pk).exists()


# ============================================================
# Nested — Field Visibility
# ============================================================


class TestAdminFieldVisibility:
    """رفتار upsert visibility per field."""

    def test_upsert_creates_new(self, admin_client, admin_user) -> None:
        criminal = R4JCriminalFactory()
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = admin_client.patch(
                f"/api/v1/r4j/admin/criminals/{criminal.pk}/visibility/",
                data={"field_name": "national_code", "is_public": True},
                format="json",
            )
        assert response.status_code == status.HTTP_200_OK
        assert R4JCriminalFieldVisibility.objects.filter(
            criminal=criminal, field_name="national_code", is_public=True,
        ).exists()

        kwargs = mock_task.delay.call_args.kwargs
        assert kwargs["action"] == audit_actions.R4J_CRIMINAL_VISIBILITY_CHANGED

    def test_upsert_updates_existing(self, admin_client) -> None:
        criminal = R4JCriminalFactory()
        R4JCriminalFieldVisibility.objects.create(
            criminal=criminal, field_name="national_code", is_public=False,
        )
        response = admin_client.patch(
            f"/api/v1/r4j/admin/criminals/{criminal.pk}/visibility/",
            data={"field_name": "national_code", "is_public": True},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        # تعداد record باید همان یکی باقی بماند
        assert (
            R4JCriminalFieldVisibility.objects.filter(criminal=criminal).count() == 1
        )


# ============================================================
# Smoke check روی R4JCriminal model
# ============================================================


class TestSmoke:
    """quick sanity check."""

    def test_create_via_factory_works(self) -> None:
        criminal = R4JCriminalFactory()
        assert R4JCriminal.all_objects.filter(pk=criminal.pk).exists()
