"""
Tests for Audit Log System — Phase Audit.3.

این فایل شامل تست‌های integration برای audit wiring روی:
- auth endpoints (login, signup, logout, password, identifier management, admin)
- tabyin endpoints (toggle, sync dispatch)

اصول تست:
- هر تست یک scenario واحد را cover می‌کند.
- async dispatch (celery) با patch کردن task در محل تعریف واقعی تست می‌شود.
- sync dispatch با بررسی DB مستقیم تست می‌شود.
- sensitive data (raw password, OTP code, token) هرگز در AuditLog نباید باشد.
- request_id propagation تست می‌شود.
- service functions از طریق namespace ماژول views patch می‌شوند
  چون view از local import استفاده می‌کند.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.models import AuditLog
from tests.factories.auth import AdminUserFactory, UserFactory
from tests.factories.tabyin import TabyinContentFactory

# ============================================================
# Constants
# ============================================================

#: مسیر واقعی task برای patch — task در tasks.py تعریف شده نه services.py.
_TASK_PATCH_PATH = "apps.audit_logs.tasks.create_audit_log_task"

#: Namespace ماژول views برای patch صحیح service functions.
#: چون view از «from .services import func» استفاده می‌کند، باید
#: local binding در views را patch کنیم نه ماژول services را.
_AUTH_VIEWS = "apps.authentication.views"


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def api_client() -> APIClient:
    """APIClient بدون احراز هویت."""
    return APIClient()


@pytest.fixture
def user(db):
    """کاربر عادی فعال با ایمیل تأیید شده."""
    return UserFactory(
        email="testuser@example.com",
        is_email_verified=True,
    )


@pytest.fixture
def admin_user(db):
    """کاربر ادمین فعال."""
    return AdminUserFactory(email="admin@example.com")


@pytest.fixture
def auth_client(user) -> APIClient:
    """APIClient احراز هویت شده با کاربر عادی."""
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


@pytest.fixture
def admin_client(admin_user) -> APIClient:
    """APIClient احراز هویت شده با کاربر ادمین."""
    client = APIClient()
    refresh = RefreshToken.for_user(admin_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


# ============================================================
# Helper
# ============================================================


def _get_latest_audit(action: str) -> AuditLog | None:
    """آخرین audit log با action مشخص."""
    return AuditLog.objects.filter(action=action).order_by("-created_at").first()


# ============================================================
# Tests — Login (password)
# ============================================================


@pytest.mark.django_db
class TestLoginPasswordAudit:
    """Audit wiring برای LoginPasswordAPIView."""

    def test_login_success_dispatches_async_audit(self, api_client, user):
        """ورود موفق باید LOGIN_SUCCESS را async dispatch کند."""
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = api_client.post(
                reverse("authentication:login-password"),
                data={
                    "identifier": "testuser@example.com",
                    "password": "StrongPass!234",
                },
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["action"] == audit_actions.LOGIN_SUCCESS
        assert call_kwargs["user_id"] == user.pk
        assert call_kwargs["resource_type"] == "user"
        assert call_kwargs["extra_data"]["method"] == "password"
        # raw password value کاربر نباید در audit باشد
        assert "StrongPass!234" not in str(call_kwargs)

    def test_login_failed_invalid_credentials_dispatches_async_audit(
        self,
        api_client,
        user,
    ):
        """ورود ناموفق باید LOGIN_FAILED را dispatch کند."""
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = api_client.post(
                reverse("authentication:login-password"),
                data={
                    "identifier": "testuser@example.com",
                    "password": "WrongPassword!",
                },
                format="json",
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["action"] == audit_actions.LOGIN_FAILED
        assert call_kwargs["user_id"] is None
        assert call_kwargs["extra_data"]["reason"] == "invalid_credentials"
        # raw password نباید در audit باشد
        assert "WrongPassword!" not in str(call_kwargs)

    def test_login_failed_inactive_account_dispatches_async_audit(
        self,
        api_client,
        db,
    ):
        """ورود به حساب غیرفعال باید LOGIN_FAILED با reason=account_inactive dispatch کند."""
        UserFactory(
            email="inactive@example.com",
            is_active=False,
            is_email_verified=True,
        )
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = api_client.post(
                reverse("authentication:login-password"),
                data={
                    "identifier": "inactive@example.com",
                    "password": "StrongPass!234",
                },
                format="json",
            )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["action"] == audit_actions.LOGIN_FAILED
        assert call_kwargs["extra_data"]["reason"] == "account_inactive"

    def test_login_request_id_propagated(self, api_client, user):
        """request_id باید در audit log ثبت شود."""
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            api_client.post(
                reverse("authentication:login-password"),
                data={
                    "identifier": "testuser@example.com",
                    "password": "StrongPass!234",
                },
                format="json",
                HTTP_X_REQUEST_ID="test-req-id-12345",
            )

        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["request_id"] == "test-req-id-12345"


# ============================================================
# Tests — Login (OTP verify)
# ============================================================


@pytest.mark.django_db
class TestLoginOTPVerifyAudit:
    """Audit wiring برای LoginOTPVerifyAPIView."""

    def test_otp_verify_failure_dispatches_login_failed_audit(self, api_client, user):
        """شکست OTP verify باید LOGIN_FAILED را dispatch کند."""
        from apps.authentication.services import OTPServiceError

        with (
            patch(
                f"{_AUTH_VIEWS}.login_otp_verify",
                side_effect=OTPServiceError(
                    "کد اشتباه است.",
                    original=Exception(),
                ),
            ),
            patch(_TASK_PATCH_PATH) as mock_task,
        ):
            mock_task.delay = MagicMock()
            response = api_client.post(
                reverse("authentication:login-otp-verify"),
                data={
                    "identifier": "testuser@example.com",
                    "code": "00000",
                },
                format="json",
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["action"] == audit_actions.LOGIN_FAILED
        assert call_kwargs["extra_data"]["method"] == "otp"
        # OTP code نباید در audit باشد
        assert "00000" not in str(call_kwargs)


# ============================================================
# Tests — Signup
# ============================================================


@pytest.mark.django_db
class TestSignupAudit:
    """Audit wiring برای SignupVerifyAPIView."""

    def test_signup_verify_success_dispatches_signup_completed_audit(
        self,
        api_client,
        db,
    ):
        """
        ثبت‌نام موفق باید SIGNUP_COMPLETED را dispatch کند.

        چون view از «from .services import signup_verify» استفاده می‌کند،
        باید local binding در views را patch کنیم تا serializer validation
        bypass شود و service مستقیم mock return کند.
        """
        fake_user = UserFactory.build(pk=999, email="newuser@example.com")
        fake_result = {
            "user": fake_user,
            "tokens": {"refresh": "r_token", "access": "a_token"},
        }

        with (
            patch(f"{_AUTH_VIEWS}.signup_verify", return_value=fake_result),
            patch(_TASK_PATCH_PATH) as mock_task,
        ):
            mock_task.delay = MagicMock()
            response = api_client.post(
                reverse("authentication:signup-verify"),
                data={
                    "identifier": "newuser@example.com",
                    "code": "12345",
                    "password": "StrongPass!234",
                },
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["action"] == audit_actions.SIGNUP_COMPLETED
        assert call_kwargs["user_id"] == fake_user.pk
        # raw password و OTP code نباید در audit باشد
        assert "StrongPass!234" not in str(call_kwargs)
        assert "12345" not in str(call_kwargs)


# ============================================================
# Tests — Logout
# ============================================================


@pytest.mark.django_db
class TestLogoutAudit:
    """Audit wiring برای LogoutAPIView."""

    def test_logout_success_dispatches_async_audit(self, auth_client, user):
        """خروج موفق باید LOGOUT را dispatch کند."""
        refresh = RefreshToken.for_user(user)

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = auth_client.post(
                reverse("authentication:logout"),
                data={"refresh": str(refresh)},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["action"] == audit_actions.LOGOUT
        assert call_kwargs["user_id"] == user.pk
        # raw refresh token نباید در audit باشد
        assert str(refresh) not in str(call_kwargs)

    def test_logout_invalid_token_no_audit(self, auth_client):
        """خروج با توکن نامعتبر نباید audit ثبت کند."""
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = auth_client.post(
                reverse("authentication:logout"),
                data={"refresh": "invalid.token.here"},
                format="json",
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        mock_task.delay.assert_not_called()


# ============================================================
# Tests — Password Change
# ============================================================


@pytest.mark.django_db
class TestPasswordChangeAudit:
    """Audit wiring برای ChangePasswordAPIView."""

    def test_password_change_success_dispatches_audit(self, auth_client, user):
        """تغییر رمز موفق باید PASSWORD_CHANGED را dispatch کند."""
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = auth_client.post(
                reverse("authentication:password-change"),
                data={
                    "old_password": "StrongPass!234",
                    "new_password": "NewStrongPass!567",
                },
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["action"] == audit_actions.PASSWORD_CHANGED
        assert call_kwargs["user_id"] == user.pk
        # raw password values نباید در audit باشد
        assert "StrongPass!234" not in str(call_kwargs)
        assert "NewStrongPass!567" not in str(call_kwargs)

    def test_password_change_wrong_old_password_no_audit(self, auth_client):
        """اگر رمز قدیمی اشتباه بود، audit نباید ثبت شود."""
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = auth_client.post(
                reverse("authentication:password-change"),
                data={
                    "old_password": "WrongOldPass!",
                    "new_password": "NewStrongPass!567",
                },
                format="json",
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        mock_task.delay.assert_not_called()


# ============================================================
# Tests — Password Reset (identifier flow)
# ============================================================


@pytest.mark.django_db
class TestPasswordResetAudit:
    """Audit wiring برای IdentifierForgotPasswordConfirmAPIView."""

    def test_password_reset_confirm_success_dispatches_audit(self, api_client, db):
        """
        بازیابی رمز موفق باید PASSWORD_RESET_COMPLETED را dispatch کند.

        چون view از «from .services import forgot_password_confirm» استفاده می‌کند،
        patch باید روی local binding در views انجام شود.
        """
        with (
            patch(f"{_AUTH_VIEWS}.forgot_password_confirm", return_value=None),
            patch(_TASK_PATCH_PATH) as mock_task,
        ):
            mock_task.delay = MagicMock()
            response = api_client.post(
                reverse("authentication:password-forgot-confirm-identifier"),
                data={
                    "identifier": "someuser@example.com",
                    "code": "12345",
                    "new_password": "NewStrongPass!567",
                },
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["action"] == audit_actions.PASSWORD_RESET_COMPLETED
        # raw OTP code و password نباید در audit باشد
        assert "12345" not in str(call_kwargs)
        assert "NewStrongPass!567" not in str(call_kwargs)


# ============================================================
# Tests — Identifier Management
# ============================================================


@pytest.mark.django_db
class TestIdentifierManagementAudit:
    """Audit wiring برای identifier add/verify/make-primary."""

    def test_identifier_add_verify_success_dispatches_audit(
        self,
        auth_client,
        user,
        db,
    ):
        """
        تأیید شناسه ثانویه باید IDENTIFIER_VERIFIED را dispatch کند.

        patch روی local binding در views انجام می‌شود.
        """
        with (
            patch(f"{_AUTH_VIEWS}.identifier_add_verify", return_value=user),
            patch(_TASK_PATCH_PATH) as mock_task,
        ):
            mock_task.delay = MagicMock()
            response = auth_client.post(
                reverse("authentication:identifier-add-verify"),
                data={
                    "identifier": "+989123456789",
                    "code": "12345",
                },
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["action"] == audit_actions.IDENTIFIER_VERIFIED
        assert call_kwargs["user_id"] == user.pk
        # raw OTP code نباید در audit باشد
        assert "12345" not in str(call_kwargs)

    def test_make_primary_dispatches_audit(self, auth_client, user, db):
        """تغییر شناسه اصلی باید PRIMARY_IDENTIFIER_CHANGED را dispatch کند."""
        from apps.authentication.models import PrimaryIdentifierKind

        user.email = "testuser@example.com"
        user.is_email_verified = True
        user.phone_number = "+989123456789"
        user.is_phone_verified = True
        user.primary_identifier = PrimaryIdentifierKind.EMAIL
        user.save(update_fields=[
            "email",
            "is_email_verified",
            "phone_number",
            "is_phone_verified",
            "primary_identifier",
        ])

        with (
            patch(f"{_AUTH_VIEWS}.make_primary_identifier", return_value=user),
            patch(_TASK_PATCH_PATH) as mock_task,
        ):
            mock_task.delay = MagicMock()
            response = auth_client.post(
                reverse("authentication:identifier-make-primary"),
                data={"identifier_kind": "phone"},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["action"] == audit_actions.PRIMARY_IDENTIFIER_CHANGED
        assert call_kwargs["user_id"] == user.pk


# ============================================================
# Tests — Admin User Operations
# ============================================================


@pytest.mark.django_db
class TestAdminUserAudit:
    """Audit wiring برای Admin endpoints."""

    def test_admin_user_delete_creates_sync_audit(self, admin_client, admin_user, db):
        """
        Soft delete کاربر توسط ادمین باید ADMIN_USER_DEACTIVATED را
        SYNCHRONOUSLY (نه async) ثبت کند.
        """
        target_user = UserFactory(email="target@example.com", is_active=True)

        response = admin_client.delete(
            reverse(
                "authentication:admin-user-detail",
                kwargs={"user_id": target_user.pk},
            ),
        )

        assert response.status_code == status.HTTP_200_OK

        # باید مستقیم در DB ثبت شده باشد (sync — نه از طریق celery)
        audit = AuditLog.objects.filter(
            action=audit_actions.ADMIN_USER_DEACTIVATED,
            resource_type="user",
            resource_id=str(target_user.pk),
        ).first()

        assert audit is not None
        assert audit.user_id == admin_user.pk
        assert audit.changes == {
            "is_active": {"before": True, "after": False},
        }

    def test_admin_role_change_creates_sync_audit(
        self,
        admin_client,
        admin_user,
        db,
    ):
        """
        تغییر نقش کاربر توسط ادمین باید ADMIN_USER_ROLE_CHANGED را
        SYNCHRONOUSLY ثبت کند.
        """
        target_user = UserFactory(email="target2@example.com")

        response = admin_client.post(
            reverse(
                "authentication:admin-user-role",
                kwargs={"user_id": target_user.pk},
            ),
            data={"role": "admin"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        audit = AuditLog.objects.filter(
            action=audit_actions.ADMIN_USER_ROLE_CHANGED,
            resource_type="user",
            resource_id=str(target_user.pk),
        ).first()

        assert audit is not None
        assert audit.user_id == admin_user.pk
        assert audit.changes["role"]["after"] == "admin"

    def test_admin_user_update_dispatches_async_audit(
        self,
        admin_client,
        admin_user,
        db,
    ):
        """ویرایش کاربر توسط ادمین باید ADMIN_USER_UPDATED را async dispatch کند."""
        target_user = UserFactory(email="target3@example.com")

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = admin_client.patch(
                reverse(
                    "authentication:admin-user-detail",
                    kwargs={"user_id": target_user.pk},
                ),
                data={"first_name": "Updated"},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["action"] == audit_actions.ADMIN_USER_UPDATED
        assert call_kwargs["user_id"] == admin_user.pk
        assert call_kwargs["resource_id"] == str(target_user.pk)

    def test_admin_deactivate_via_patch_dispatches_deactivated_event(
        self,
        admin_client,
        admin_user,
        db,
    ):
        """
        اگر admin از طریق PATCH کاربر را deactivate کند،
        باید ADMIN_USER_DEACTIVATED dispatch شود (نه ADMIN_USER_UPDATED).
        """
        target_user = UserFactory(email="target4@example.com", is_active=True)

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = admin_client.patch(
                reverse(
                    "authentication:admin-user-detail",
                    kwargs={"user_id": target_user.pk},
                ),
                data={"is_active": False},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["action"] == audit_actions.ADMIN_USER_DEACTIVATED


# ============================================================
# Tests — Tabyin Toggle
# ============================================================


@pytest.mark.django_db
class TestTabyinToggleAudit:
    """Audit wiring برای AdminTabyinContentToggleView."""

    def test_toggle_content_dispatches_async_audit(
        self,
        admin_client,
        admin_user,
        db,
    ):
        """Toggle محتوا باید TABYIN_CONTENT_TOGGLED را async dispatch کند."""
        content = TabyinContentFactory(is_active=True)

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = admin_client.patch(
                reverse(
                    "tabyin:admin-content-toggle",
                    kwargs={"external_id": content.external_id},
                ),
                data={"is_active": False},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["action"] == audit_actions.TABYIN_CONTENT_TOGGLED
        assert call_kwargs["resource_type"] == "tabyin_content"
        assert call_kwargs["resource_id"] == content.external_id
        assert call_kwargs["user_id"] == admin_user.pk
        assert call_kwargs["changes"]["is_active"]["before"] is True
        assert call_kwargs["changes"]["is_active"]["after"] is False

    def test_toggle_content_change_data_in_audit(
        self,
        admin_client,
        admin_user,
        db,
    ):
        """changes باید before/after صحیح را داشته باشد."""
        content = TabyinContentFactory(is_active=False)

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            admin_client.patch(
                reverse(
                    "tabyin:admin-content-toggle",
                    kwargs={"external_id": content.external_id},
                ),
                data={"is_active": True},
                format="json",
            )

        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["changes"]["is_active"]["before"] is False
        assert call_kwargs["changes"]["is_active"]["after"] is True


# ============================================================
# Tests — Tabyin Sync Dispatch
# ============================================================


@pytest.mark.django_db
class TestTabyinSyncDispatchAudit:
    """Audit wiring برای AdminSyncTriggerView."""

    def test_sync_dispatch_dispatches_audit(self, admin_client, admin_user, db):
        """Dispatch sync باید TABYIN_SYNC_DISPATCHED را async dispatch کند."""
        fake_task_id = "fake-task-id-abc123"

        with (
            patch(
                "apps.tabyin.services.dispatch_sync_task",
                return_value=fake_task_id,
            ),
            patch(_TASK_PATCH_PATH) as mock_task,
        ):
            mock_task.delay = MagicMock()
            response = admin_client.post(
                reverse("tabyin:admin-sync-trigger"),
                data={"mode": "incremental"},
                format="json",
            )

        assert response.status_code == status.HTTP_202_ACCEPTED
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["action"] == audit_actions.TABYIN_SYNC_DISPATCHED
        assert call_kwargs["resource_type"] == "tabyin_sync"
        assert call_kwargs["resource_id"] == fake_task_id
        assert call_kwargs["user_id"] == admin_user.pk
        assert call_kwargs["extra_data"]["mode"] == "incremental"

    def test_sync_dispatch_full_mode_in_audit(self, admin_client, admin_user, db):
        """mode=full باید در extra_data ثبت شود."""
        fake_task_id = "fake-task-id-xyz999"

        with (
            patch(
                "apps.tabyin.services.dispatch_sync_task",
                return_value=fake_task_id,
            ),
            patch(_TASK_PATCH_PATH) as mock_task,
        ):
            mock_task.delay = MagicMock()
            admin_client.post(
                reverse("tabyin:admin-sync-trigger"),
                data={"mode": "full"},
                format="json",
            )

        call_kwargs = mock_task.delay.call_args.kwargs
        assert call_kwargs["extra_data"]["mode"] == "full"


# ============================================================
# Tests — Audit Model Immutability
# ============================================================


@pytest.mark.django_db
class TestAuditLogImmutability:
    """AuditLog model نباید قابل حذف یا soft-delete باشد."""

    def test_soft_delete_raises_permission_error(self, db):
        """soft_delete روی AuditLog باید PermissionError بدهد."""
        user = UserFactory()
        audit = AuditLog.objects.create(
            user=user,
            action=audit_actions.LOGIN_SUCCESS,
            resource_type="user",
            resource_id=str(user.pk),
        )

        with pytest.raises(PermissionError):
            audit.soft_delete()

    def test_restore_raises_permission_error(self, db):
        """restore روی AuditLog باید PermissionError بدهد."""
        user = UserFactory()
        audit = AuditLog.objects.create(
            user=user,
            action=audit_actions.LOGIN_SUCCESS,
            resource_type="user",
            resource_id=str(user.pk),
        )

        with pytest.raises(PermissionError):
            audit.restore()


# ============================================================
# Tests — Sensitive Data Redaction (global regression)
# ============================================================


@pytest.mark.django_db
class TestSensitiveDataNotInAudit:
    """هیچ sensitive data نباید در AuditLog ثبت شود."""

    def test_admin_delete_audit_has_no_sensitive_fields(
        self,
        admin_client,
        admin_user,
        db,
    ):
        """Audit log برای delete نباید هیچ raw password یا token داشته باشد."""
        target_user = UserFactory(email="victim@example.com", is_active=True)

        admin_client.delete(
            reverse(
                "authentication:admin-user-detail",
                kwargs={"user_id": target_user.pk},
            ),
        )

        audit = AuditLog.objects.filter(
            action=audit_actions.ADMIN_USER_DEACTIVATED,
            resource_id=str(target_user.pk),
        ).first()

        assert audit is not None
        # بررسی می‌کنیم هیچ raw credential در changes یا extra_data نیست
        audit_str = str(audit.changes) + str(audit.extra_data)
        assert "pbkdf2" not in audit_str.lower()
        assert "eyj" not in audit_str.lower()
        assert "secret" not in audit_str.lower()


# ============================================================
# Tests — Phase Audit.5 — Admin Audit Log API
# ============================================================


@pytest.mark.django_db
class TestAdminAuditLogListAPI:
    """تست‌های admin audit log list endpoint."""

    def test_list_returns_paginated_audit_logs(self, admin_client, admin_user, db):
        """لیست audit logs باید paginated و 200 برگرداند."""
        # ساخت چند audit log
        from tests.factories.audit_logs import AuditLogFactory

        AuditLogFactory.create_batch(5, user=admin_user)

        response = admin_client.get(
            reverse("audit_logs:admin-log-list"),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert "results" in response.data["data"]
        assert response.data["data"]["count"] >= 5

    def test_list_filter_by_action(self, admin_client, admin_user, db):
        """فیلتر بر اساس action باید فقط action مربوطه را برگرداند."""
        from tests.factories.audit_logs import AuditLogFactory

        AuditLogFactory(user=admin_user, action=audit_actions.LOGIN_SUCCESS)
        AuditLogFactory(user=admin_user, action=audit_actions.LOGOUT)
        AuditLogFactory(user=admin_user, action=audit_actions.LOGIN_SUCCESS)

        response = admin_client.get(
            reverse("audit_logs:admin-log-list"),
            {"action": audit_actions.LOGIN_SUCCESS},
        )

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert len(results) == 2
        assert all(r["action"] == audit_actions.LOGIN_SUCCESS for r in results)

    def test_list_filter_by_resource_type(self, admin_client, admin_user, db):
        """فیلتر بر اساس resource_type."""
        from tests.factories.audit_logs import AuditLogFactory

        AuditLogFactory(user=admin_user, resource_type="user")
        AuditLogFactory(user=admin_user, resource_type="report")

        response = admin_client.get(
            reverse("audit_logs:admin-log-list"),
            {"resource_type": "report"},
        )

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert len(results) == 1
        assert results[0]["resource_type"] == "report"

    def test_list_filter_by_request_id(self, admin_client, admin_user, db):
        """فیلتر بر اساس request_id."""
        from tests.factories.audit_logs import AuditLogFactory

        AuditLogFactory(user=admin_user, request_id="unique-req-123")
        AuditLogFactory(user=admin_user, request_id="other-req-456")

        response = admin_client.get(
            reverse("audit_logs:admin-log-list"),
            {"request_id": "unique-req-123"},
        )

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert len(results) == 1
        assert results[0]["request_id"] == "unique-req-123"

    def test_list_filter_by_ip_address(self, admin_client, admin_user, db):
        """فیلتر بر اساس IP."""
        from tests.factories.audit_logs import AuditLogFactory

        AuditLogFactory(user=admin_user, ip_address="10.0.0.1")
        AuditLogFactory(user=admin_user, ip_address="192.168.1.1")

        response = admin_client.get(
            reverse("audit_logs:admin-log-list"),
            {"ip_address": "10.0.0.1"},
        )

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert len(results) == 1

    def test_list_search(self, admin_client, admin_user, db):
        """جستجوی متنی در action و resource_type."""
        from tests.factories.audit_logs import AuditLogFactory

        AuditLogFactory(
            user=admin_user,
            action=audit_actions.LOGIN_SUCCESS,
            resource_type="user",
        )
        AuditLogFactory(
            user=admin_user,
            action=audit_actions.REPORT_CREATED,
            resource_type="report",
        )

        response = admin_client.get(
            reverse("audit_logs:admin-log-list"),
            {"search": "REPORT"},
        )

        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert len(results) == 1

    def test_list_unauthenticated_returns_401(self, api_client, db):
        """دسترسی بدون auth باید 401 برگرداند."""
        response = api_client.get(
            reverse("audit_logs:admin-log-list"),
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_non_admin_returns_403(self, db):
        """کاربر عادی (غیر ادمین) باید 403 بگیرد."""
        user = UserFactory(email="regular@example.com", is_email_verified=True)
        client = APIClient()
        refresh = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")

        response = client.get(
            reverse("audit_logs:admin-log-list"),
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestAdminAuditLogDetailAPI:
    """تست‌های admin audit log detail endpoint."""

    def test_detail_returns_full_audit_log(self, admin_client, admin_user, db):
        """جزئیات باید changes و extra_data را شامل شود."""
        from tests.factories.audit_logs import AuditLogFactory

        audit = AuditLogFactory(
            user=admin_user,
            action=audit_actions.ADMIN_USER_ROLE_CHANGED,
            resource_type="user",
            resource_id="42",
            changes={"role": {"before": "user", "after": "admin"}},
            extra_data={"triggered_by": "admin_panel"},
        )

        response = admin_client.get(
            reverse(
                "audit_logs:admin-log-detail",
                kwargs={"audit_log_id": audit.pk},
            ),
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert data["id"] == audit.pk
        assert data["action"] == audit_actions.ADMIN_USER_ROLE_CHANGED
        assert data["changes"]["role"]["after"] == "admin"
        assert data["extra_data"]["triggered_by"] == "admin_panel"
        assert data["user"]["id"] == admin_user.pk

    def test_detail_not_found_returns_404(self, admin_client, db):
        """شناسه نامعتبر باید 404 برگرداند."""
        response = admin_client.get(
            reverse(
                "audit_logs:admin-log-detail",
                kwargs={"audit_log_id": 99999},
            ),
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_detail_anonymous_user_audit_shows_null_user(
        self,
        admin_client,
        db,
    ):
        """audit log بدون user باید user=null نمایش دهد."""
        audit = AuditLog.objects.create(
            user=None,
            action=audit_actions.REPORT_CREATED,
            resource_type="report",
            resource_id="7",
        )

        response = admin_client.get(
            reverse(
                "audit_logs:admin-log-detail",
                kwargs={"audit_log_id": audit.pk},
            ),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["user"] is None

    def test_detail_unauthenticated_returns_401(self, api_client, db):
        """دسترسی بدون auth باید 401 برگرداند."""
        response = api_client.get(
            reverse(
                "audit_logs:admin-log-detail",
                kwargs={"audit_log_id": 1},
            ),
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
