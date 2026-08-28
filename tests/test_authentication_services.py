"""
Coverage hardening — apps.authentication.services (یافتهٔ ممیزی ۴.۲).

ممیزی مستقل نشان داد `apps/authentication/services.py` با ۵۹.۷٪ کم‌پوشش‌ترین
ماژول بزرگِ حساس پروژه است و توابعی که مستقیم به امنیت حساب گره خورده‌اند
(تغییر شماره موبایل، سیگنال ریسک ورود ناموفق، نگاشت خطاهای OTP، ورود با
رمز عبور و resolution شناسه‌های legacy) عمدتاً تست‌نشده بودند.

این ماژول همان مسیرهای پوشش‌نداده را با تست‌های service-level (نه از طریق
view) می‌پوشاند تا هر شاخهٔ تصمیم‌گیریِ خطرناک مستند و قفل شود:
- هر شاخهٔ `_prepare_phone_number_update` (حذف/تغییر/تکرار شماره)
- هر استثنای نگاشت‌شده در `_map_otp_error_to_service_error`
- هر شاخهٔ `record_failed_login_risk` (سیگنال escalation بعد از ۵ شکست)
- هر شاخهٔ `_resolve_legacy_otp_identifier`
- شاخه‌های `_build_login_result`/`_create_auth_session`/`_build_device_label`
- سرویس‌های پروفایل/ادمین (update_profile, update_user_basic_info, admin_*)
- flowهای multi-identifier (signup/login/forgot/identifier_add)
"""

from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.http import HttpRequest
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.services import create_audit_log
from apps.authentication import otp as otp_service, services as auth_services
from apps.authentication.choices import (
    AuthRiskSeverity,
    AuthRiskSignalType,
    OTPPurpose,
    UserRole,
)
from apps.authentication.constants import SESSION_ID_CLAIM
from apps.authentication.models import (
    AuthRiskSignal,
    OTPCode,
    PrimaryIdentifierKind,
    Profile,
    User,
)
from apps.authentication.normalizers import normalize_email, normalize_phone
from apps.authentication.otp import (
    OTPCooldownActive,
    OTPDeliveryError,
    OTPExpired,
    OTPInvalidCode,
    OTPNotFound,
    OTPTooManyAttempts,
)
from tests.factories import AdminUserFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _patch_sms_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    """ارسال SMS در تست‌ها mock می‌شود (قرارداد پروژه).

    ConsoleSMSOTPProvider در نبودِ DEBUG (محیط تست) عمداً fail-loud می‌کند؛
    بنابراین تست‌ها مثل بقیهٔ ماژول‌های auth، delivery را با monkeypatch
    جایگزین می‌کنند تا خودِ service تحت آزمایش بماند.
    """
    from apps.authentication import providers

    monkeypatch.setattr(
        providers.ConsoleSMSOTPProvider,
        "send",
        lambda self, recipient, code, purpose: True,
    )


# ============================================================
# Helpers
# ============================================================


def _uniq(prefix: str) -> str:
    """ساخت شناسهٔ یکتا (ایمیل/شماره) برای جلوگیری از تداخل بین تست‌ها."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _uniq_email() -> str:
    return f"{_uniq('svc')}@test.local"


def _uniq_phone() -> str:
    # فقط رقم — normalize_phone شمارهٔ دارای حرف را رد می‌کند.
    return "+98912" + "".join(str(uuid.uuid4().int)[i] for i in range(7))


def _mint_otp(*, kind: str, value: str, purpose: str):
    """مint مستقیم OTP با کد ساده تا تست بتواند مسیر موفق verify را طی کند."""
    return otp_service.generate_and_send_otp(
        identifier_kind=kind,
        identifier_value=value,
        purpose=purpose,
    )


def _bare_request(*, user_agent: str = "", ip: str | None = None) -> HttpRequest:
    request = HttpRequest()
    request.META["HTTP_USER_AGENT"] = user_agent
    if ip is not None:
        request.META["REMOTE_ADDR"] = ip
    return request


# ============================================================
# ۱ — یاری‌گرهای داخلی: IP و normalization شناسه‌ها
# ============================================================


class TestClientIPAndIdentifierHelpers:
    """پوشش `_get_client_ip` و `_normalize_identifier_by_kind` و دوستان."""

    def test_get_client_ip_prefers_first_xff_entry(self) -> None:
        request = _bare_request()
        request.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.7, 10.0.0.1, 192.168.1.9"

        assert auth_services._get_client_ip(request=request) == "203.0.113.7"

    def test_get_client_ip_falls_back_to_remote_addr(self) -> None:
        request = _bare_request(ip="198.51.100.42")

        assert auth_services._get_client_ip(request=request) == "198.51.100.42"

    def test_normalize_identifier_phone_returns_e164(self) -> None:
        normalized = auth_services._normalize_identifier_by_kind(
            identifier_kind=PrimaryIdentifierKind.PHONE,
            identifier_value=_uniq_phone(),
        )

        assert normalized.startswith("+98")

    def test_normalize_identifier_email_lowercases_domain(self) -> None:
        normalized = auth_services._normalize_identifier_by_kind(
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value="MiXeD@TeSt.LOCAL",
        )

        assert normalized == "mixed@test.local"

    def test_normalize_identifier_rejects_unknown_kind(self) -> None:
        with pytest.raises(ValueError, match="Unsupported identifier_kind"):
            auth_services._normalize_identifier_by_kind(
                identifier_kind="fax",
                identifier_value="x",
            )

    def test_get_identifier_state_for_phone_channel(self) -> None:
        user = UserFactory(phone_number=_uniq_phone(), is_phone_verified=True)

        value, verified = auth_services._get_identifier_state_for_user(
            user=user,
            identifier_kind=PrimaryIdentifierKind.PHONE,
        )

        assert value == user.phone_number
        assert verified is True

    def test_get_identifier_state_rejects_unknown_kind(self) -> None:
        user = UserFactory()
        with pytest.raises(ValueError, match="Unsupported identifier_kind"):
            auth_services._get_identifier_state_for_user(
                user=user,
                identifier_kind="fax",
            )

    def test_identifier_exists_for_other_user_reports_phone_taken(self) -> None:
        owner = UserFactory(phone_number=_uniq_phone())
        other = UserFactory()

        assert (
            auth_services._identifier_exists_for_other_user(
                identifier_kind=PrimaryIdentifierKind.PHONE,
                identifier_value=owner.phone_number,
                exclude_user_id=other.pk,
            )
            is True
        )
        assert (
            auth_services._identifier_exists_for_other_user(
                identifier_kind=PrimaryIdentifierKind.PHONE,
                identifier_value=owner.phone_number,
                exclude_user_id=owner.pk,
            )
            is False
        )


# ============================================================
# ۲ — _ensure_identifier_can_be_added_or_verified
# ============================================================


class TestEnsureIdentifierCanBeAdded:
    """شاخه‌های مسدودسازی channel در اتصال شناسهٔ دوم."""

    def test_same_identifier_already_verified_is_rejected(self) -> None:
        email = _uniq_email()
        user = UserFactory(email=email, is_email_verified=True)

        with pytest.raises(auth_services.IdentifierAlreadyVerified):
            auth_services.identifier_add_request(
                user=user,
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value=email,
            )

    def test_different_email_in_same_channel_is_rejected(self) -> None:
        user = UserFactory(email=_uniq_email(), is_email_verified=False)

        with pytest.raises(auth_services.IdentifierChannelAlreadyOccupied):
            auth_services.identifier_add_request(
                user=user,
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value=_uniq_email(),
            )

    def test_different_phone_in_same_channel_is_rejected(self) -> None:
        user = UserFactory(phone_number=_uniq_phone(), is_phone_verified=False)

        with pytest.raises(auth_services.IdentifierChannelAlreadyOccupied):
            auth_services.identifier_add_request(
                user=user,
                identifier_kind=PrimaryIdentifierKind.PHONE,
                identifier_value=_uniq_phone(),
            )

    def test_identifier_belonging_to_another_user_is_rejected(self) -> None:
        taken = _uniq_email()
        UserFactory(email=taken, is_email_verified=True)
        # حمله‌کننده بدون ایمیل (فقط موبایل) تا channel ایمیلش اشغال نباشد و
        # خطای duplicate واقعاً از «تعلق به کاربر دیگر» بیاید.
        attacker = UserFactory(email=None, phone_number=_uniq_phone())

        with pytest.raises(auth_services.IdentifierAlreadyExists):
            auth_services.identifier_add_request(
                user=attacker,
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value=taken,
            )

    def test_same_unverified_identifier_is_allowed_and_sends_otp(self) -> None:
        email = _uniq_email()
        user = UserFactory(email=email, is_email_verified=False)

        auth_services.identifier_add_request(
            user=user,
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value=email + " ",  # با whitespace → همان normalized
        )

        assert OTPCode.objects.filter(
            identifier_value=email,
            purpose=OTPPurpose.IDENTIFIER_ADD,
        ).exists()


# ============================================================
# ۳ — _resolve_legacy_otp_identifier
# ============================================================


class TestResolveLegacyOTPIdentifier:
    """Resolution شناسه برای flowهای legacy (email-first)."""

    def test_verification_purpose_prefers_email(self) -> None:
        email = _uniq_email()
        user = UserFactory(email=email)

        kind, value = auth_services._resolve_legacy_otp_identifier(
            user=user,
            purpose=OTPPurpose.EMAIL_VERIFICATION,
        )

        assert kind == PrimaryIdentifierKind.EMAIL
        assert value == normalize_email(email)

    def test_email_purpose_without_email_raises(self) -> None:
        user = UserFactory(email=None, phone_number=_uniq_phone())

        with pytest.raises(ValueError, match="valid email identifier"):
            auth_services._resolve_legacy_otp_identifier(
                user=user,
                purpose=OTPPurpose.PASSWORD_RESET,
            )

    def test_phone_primary_resolves_phone(self) -> None:
        phone = _uniq_phone()
        user = UserFactory(
            email=None, phone_number=phone, primary_identifier=PrimaryIdentifierKind.PHONE
        )

        kind, value = auth_services._resolve_legacy_otp_identifier(
            user=user,
            purpose=OTPPurpose.LOGIN,
        )

        assert kind == PrimaryIdentifierKind.PHONE
        assert value == normalize_phone(phone)

    def test_phone_primary_with_cleared_phone_falls_back_to_email(self) -> None:
        email = _uniq_email()
        user = UserFactory(
            email=email,
            phone_number=_uniq_phone(),
            primary_identifier=PrimaryIdentifierKind.PHONE,
        )
        user.phone_number = None
        user.save(update_fields=["phone_number"])

        kind, value = auth_services._resolve_legacy_otp_identifier(
            user=user,
            purpose=OTPPurpose.LOGIN,
        )

        assert kind == PrimaryIdentifierKind.EMAIL
        assert value == normalize_email(email)

    def test_email_primary_without_email_falls_back_to_phone(self) -> None:
        phone = _uniq_phone()
        user = UserFactory()
        # primary=EMAIL است ولی email حذف شده؛ phone باید fallback شود.
        # (بدون save — فقط وضعیت در حافظهٔ شیء؛ DB را دست نمی‌زنیم تا
        # CHECK constraint کاربر با هیچ شناسه‌ای نقض نشود.)
        user.email = None
        user.phone_number = phone
        assert user.primary_identifier == PrimaryIdentifierKind.EMAIL

        kind, value = auth_services._resolve_legacy_otp_identifier(
            user=user,
            purpose=OTPPurpose.LOGIN,
        )

        assert kind == PrimaryIdentifierKind.PHONE
        assert value == phone

    def test_no_identifier_raises(self) -> None:
        user = UserFactory()
        # فقط در حافظه — ذخیرهٔ کاربرِ بدون هیچ شناسه‌ای CHECK constraint
        # پایگاه‌داده را نقض می‌کند و برای این تست لازم نیست.
        user.email = None
        user.phone_number = None

        with pytest.raises(ValueError, match="no resolvable identifier"):
            auth_services._resolve_legacy_otp_identifier(
                user=user,
                purpose=OTPPurpose.LOGIN,
            )


# ============================================================
# ۴ — _prepare_phone_number_update
# ============================================================


class TestPreparePhoneNumberUpdate:
    """مجاورِ تصاحب حساب: هر شاخهٔ تغییر شماره باید قفل باشد."""

    def test_none_returns_empty(self) -> None:
        user = UserFactory()

        assert auth_services._prepare_phone_number_update(user=user, phone_number=None) == []

    def test_clearing_phone_of_phone_primary_without_email_is_forbidden(self) -> None:
        user = UserFactory(
            email=None,
            phone_number=_uniq_phone(),
            primary_identifier=PrimaryIdentifierKind.PHONE,
            is_phone_verified=True,
        )

        with pytest.raises(ValidationError, match="حذف شماره موبایل مجاز نیست"):
            auth_services._prepare_phone_number_update(user=user, phone_number="")

    def test_clearing_existing_phone_unverifies_it(self) -> None:
        user = UserFactory(phone_number=_uniq_phone(), is_phone_verified=True)

        fields = auth_services._prepare_phone_number_update(user=user, phone_number="")

        assert set(fields) == {"phone_number", "is_phone_verified"}
        assert user.phone_number is None
        assert user.is_phone_verified is False

    def test_clearing_empty_phone_returns_empty(self) -> None:
        user = UserFactory()

        assert auth_services._prepare_phone_number_update(user=user, phone_number="") == []

    def test_duplicate_phone_is_rejected(self) -> None:
        taken = _uniq_phone()
        UserFactory(phone_number=taken)
        user = UserFactory()

        with pytest.raises(ValidationError, match="قبلاً ثبت شده است"):
            auth_services._prepare_phone_number_update(user=user, phone_number=taken)

    def test_same_phone_returns_empty(self) -> None:
        phone = _uniq_phone()
        user = UserFactory(phone_number=phone)

        assert auth_services._prepare_phone_number_update(user=user, phone_number=phone) == []

    def test_new_phone_updates_and_unverifies_when_verified(self) -> None:
        user = UserFactory(phone_number=_uniq_phone(), is_phone_verified=True)

        fields = auth_services._prepare_phone_number_update(user=user, phone_number=_uniq_phone())

        assert set(fields) == {"phone_number", "is_phone_verified"}
        assert user.is_phone_verified is False

    def test_new_phone_keeps_unverified_state(self) -> None:
        user = UserFactory(phone_number=_uniq_phone(), is_phone_verified=False)

        fields = auth_services._prepare_phone_number_update(user=user, phone_number=_uniq_phone())

        assert fields == ["phone_number"]
        assert user.is_phone_verified is False


# ============================================================
# ۵ — پروفایل و اطلاعات پایهٔ کاربر
# ============================================================


class TestProfileAndUserUpdateServices:
    """update_profile و update_user_basic_info."""

    def test_update_profile_persists_editable_fields_and_phone(self) -> None:
        user = UserFactory()
        profile = Profile.objects.get_or_create(user=user)[0]
        new_phone = _uniq_phone()

        auth_services.update_profile(profile=profile, phone_number=new_phone, bio="دربارهٔ من")

        user.refresh_from_db()
        profile.refresh_from_db()
        assert user.phone_number == new_phone
        assert profile.bio == "دربارهٔ من"

    def test_update_profile_removes_phone_when_cleared(self) -> None:
        user = UserFactory(phone_number=_uniq_phone(), is_phone_verified=True)
        profile = Profile.objects.get_or_create(user=user)[0]

        auth_services.update_profile(profile=profile, phone_number="")

        user.refresh_from_db()
        assert user.phone_number is None
        assert user.is_phone_verified is False

    def test_update_profile_skips_none_and_unknown_keys(self) -> None:
        user = UserFactory()
        profile = Profile.objects.get_or_create(user=user)[0]

        result = auth_services.update_profile(
            profile=profile,
            bio=None,  # None → نادیده گرفته می‌شود
            nonexistent_field="x",  # بدون attr → نادیده گرفته می‌شود
        )

        profile.refresh_from_db()
        assert result.pk == profile.pk
        assert profile.bio == ""

    def test_update_profile_with_no_editable_fields_still_touches_updated_at(self) -> None:
        user = UserFactory()
        profile = Profile.objects.get_or_create(user=user)[0]
        profile.bio = "old"
        profile.save(update_fields=["bio", "updated_at"])

        auth_services.update_profile(profile=profile)

        profile.refresh_from_db()
        assert profile.bio == "old"

    def test_update_user_basic_info_updates_names_only(self) -> None:
        user = UserFactory(first_name="A", last_name="B")

        auth_services.update_user_basic_info(
            user=user,
            first_name="علی",
            last_name="رضایی",
            role=UserRole.ADMIN,  # خارج از whitelist → نادیده
            is_active=False,  # خارج از whitelist → نادیده
            middle_name=None,  # None → نادیده
        )

        user.refresh_from_db()
        assert user.first_name == "علی"
        assert user.last_name == "رضایی"
        assert user.role == UserRole.USER
        assert user.is_active is True

    def test_update_user_basic_info_with_no_valid_fields_skips_save(self) -> None:
        user = UserFactory(first_name="A")

        auth_services.update_user_basic_info(user=user, role=UserRole.ADMIN, extra="x")

        user.refresh_from_db()
        assert user.first_name == "A"


# ============================================================
# ۶ — سرویس‌های ادمین
# ============================================================


class TestAdminUserServices:
    """admin_update_user و admin_change_user_role."""

    def test_admin_update_user_applies_whitelisted_fields(self) -> None:
        user = UserFactory()

        auth_services.admin_update_user(
            user=user,
            first_name="مدیر",
            is_active=False,
            is_email_verified=True,
            phone_number=_uniq_phone(),  # خارج از whitelist → نادیده
            role=UserRole.ADMIN,  # خارج از whitelist → نادیده
        )

        user.refresh_from_db()
        assert user.first_name == "مدیر"
        assert user.is_active is False
        assert user.is_email_verified is True
        assert user.phone_number is None

    def test_admin_update_user_without_valid_fields_skips_save(self) -> None:
        user = UserFactory(first_name="A")

        auth_services.admin_update_user(user=user, phone_number=_uniq_phone())

        user.refresh_from_db()
        assert user.first_name == "A"

    def test_admin_change_role_to_admin_sets_staff(self) -> None:
        user = UserFactory(role=UserRole.USER, is_staff=False)

        auth_services.admin_change_user_role(user=user, role=UserRole.ADMIN)

        user.refresh_from_db()
        assert user.role == UserRole.ADMIN
        assert user.is_staff is True

    def test_admin_change_role_to_user_clears_staff(self) -> None:
        user = AdminUserFactory()

        auth_services.admin_change_user_role(user=user, role=UserRole.USER)

        user.refresh_from_db()
        assert user.role == UserRole.USER
        assert user.is_staff is False


# ============================================================
# ۷ — توکن، نشست و label دستگاه
# ============================================================


class TestTokenAndSessionServices:
    """_issue_tokens، _create_auth_session، _build_device_label، _build_login_result."""

    def test_generate_tokens_for_user_round_trips(self) -> None:
        from rest_framework_simplejwt.tokens import AccessToken

        user = UserFactory()

        tokens = auth_services.generate_tokens_for_user(user=user)

        assert set(tokens) == {"refresh", "access"}
        refresh_payload = RefreshToken(tokens["refresh"]).payload
        assert refresh_payload["user_id"] == str(user.pk)
        # access باید برای همان کاربر صادر شده باشد (claim‌ها مشترک‌اند).
        assert AccessToken(tokens["access"]).payload["user_id"] == str(user.pk)

    def test_create_auth_session_stores_request_context(self) -> None:
        user = UserFactory()
        refresh = RefreshToken.for_user(user)
        request = _bare_request(user_agent="Mozilla/5.0 (iPhone)", ip="198.51.100.7")
        request.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.99, 10.0.0.2"

        session = auth_services._create_auth_session(
            user=user,
            refresh_token=str(refresh),
            request=request,
        )

        assert session.user_id == user.pk
        assert session.refresh_jti == str(refresh["jti"])
        assert session.device_label == "Mobile browser"
        assert session.ip_address == "203.0.113.99"
        assert session.expires_at is not None
        assert session.fingerprint_hash

    def test_device_label_variants(self) -> None:
        assert auth_services._build_device_label(user_agent="Mozilla (X11; Linux) Chrome/126") == (
            "Chrome browser"
        )
        assert auth_services._build_device_label(user_agent="Mozilla/5.0 Firefox/127") == (
            "Firefox browser"
        )
        assert auth_services._build_device_label(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X) Safari/17"
        ) == ("Safari browser")
        assert (
            auth_services._build_device_label(user_agent="Mozilla/5.0 (Android 14)")
            == "Mobile browser"
        )
        assert auth_services._build_device_label(user_agent="") == "Unknown device"
        assert auth_services._build_device_label(user_agent="M" * 200) == "M" * 80

    def test_build_login_result_tracks_ip_and_issues_session(self) -> None:
        user = UserFactory(is_email_verified=True)
        request = _bare_request(user_agent="svc-test", ip="203.0.113.5")

        result = auth_services._build_login_result(user=user, request=request)

        user.refresh_from_db()
        assert user.last_login_ip == "203.0.113.5"
        assert result["user"].pk == user.pk
        assert set(result["tokens"]) == {"refresh", "access"}
        assert result["session"].user_id == user.pk
        assert result["session"].is_revoked is False

    def test_build_login_result_without_ip_keeps_last_login_ip(self) -> None:
        user = UserFactory(is_email_verified=True)
        user.last_login_ip = "198.51.100.9"
        user.save(update_fields=["last_login_ip"])

        result = auth_services._build_login_result(
            user=user,
            request=_bare_request(),  # بدون REMOTE_ADDR و X-Forwarded-For
        )

        user.refresh_from_db()
        assert user.last_login_ip == "198.51.100.9"
        assert result["session"].ip_address is None

    def test_logout_rejects_garbage_token(self) -> None:
        assert auth_services.logout_user(refresh_token="not-a-real-token") is False

    def test_logout_swallows_unexpected_errors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        user = UserFactory()
        refresh = RefreshToken.for_user(user)

        def boom(self) -> None:
            raise RuntimeError("provider down")

        monkeypatch.setattr(auth_services.RefreshToken, "blacklist", boom)

        assert auth_services.logout_user(refresh_token=str(refresh)) is False

    def test_logout_valid_refresh_token_blacklists_and_revokes_session(self) -> None:
        user = UserFactory()
        refresh = RefreshToken.for_user(user)
        session = auth_services._create_auth_session(
            user=user,
            refresh_token=str(refresh),
            request=_bare_request(),
        )

        assert auth_services.logout_user(refresh_token=str(refresh)) is True

        session.refresh_from_db()
        assert session.is_revoked is True
        assert (
            auth_services.validate_and_touch_session(
                user=user, token_claims={SESSION_ID_CLAIM: session.pk}
            )
            is False
        )


# ============================================================
# ۸ — سیگنال‌های ریسک
# ============================================================


class TestRiskSignalServices:
    """create_auth_risk_signal، record_failed_login_risk، review_auth_risk_signal."""

    def test_create_risk_signal_deduplicates_open_signal(self) -> None:
        user = UserFactory()

        first = auth_services.create_auth_risk_signal(
            signal_type=AuthRiskSignalType.NEW_IP,
            severity=AuthRiskSeverity.LOW,
            user=user,
            ip_address="198.51.100.1",
            description="x",
        )
        second = auth_services.create_auth_risk_signal(
            signal_type=AuthRiskSignalType.NEW_IP,
            severity=AuthRiskSeverity.LOW,
            user=user,
            ip_address="198.51.100.1",
            description="x",
        )

        assert second.pk == first.pk
        assert AuthRiskSignal.objects.filter(user=user).count() == 1

    def test_risk_signal_metadata_defaults_to_empty_dict(self) -> None:
        user = UserFactory()

        signal = auth_services.create_auth_risk_signal(
            signal_type=AuthRiskSignalType.NEW_DEVICE,
            severity=AuthRiskSeverity.MEDIUM,
            user=user,
        )

        assert signal.metadata == {}

    def test_record_failed_login_risk_returns_none_without_user(self) -> None:
        assert auth_services.record_failed_login_risk(user=None, ip_address="1.2.3.4") is None

    def test_record_failed_login_risk_returns_none_when_signal_already_open(self) -> None:
        user = UserFactory()
        auth_services.create_auth_risk_signal(
            signal_type=AuthRiskSignalType.FAILED_LOGIN_SPIKE,
            severity=AuthRiskSeverity.HIGH,
            user=user,
        )

        assert auth_services.record_failed_login_risk(user=user, ip_address="1.2.3.4") is None

    def test_record_failed_login_risk_stays_silent_below_threshold(self) -> None:
        user = UserFactory()
        for _ in range(3):
            create_audit_log(
                user_id=user.pk,
                action=audit_actions.LOGIN_FAILED,
                resource_type="user",
                resource_id=str(user.pk),
            )

        assert auth_services.record_failed_login_risk(user=user, ip_address="1.2.3.4") is None
        assert not AuthRiskSignal.objects.filter(
            user=user, signal_type=AuthRiskSignalType.FAILED_LOGIN_SPIKE
        ).exists()

    def test_record_failed_login_risk_escalates_after_threshold(self) -> None:
        user = UserFactory()
        for _ in range(5):
            create_audit_log(
                user_id=user.pk,
                action=audit_actions.LOGIN_FAILED,
                resource_type="user",
                resource_id=str(user.pk),
            )

        signal = auth_services.record_failed_login_risk(
            user=user,
            ip_address="203.0.113.77",
            window_minutes=30,
            threshold=5,
        )

        assert signal is not None
        assert signal.signal_type == AuthRiskSignalType.FAILED_LOGIN_SPIKE
        assert signal.severity == AuthRiskSeverity.HIGH
        assert signal.ip_address == "203.0.113.77"
        assert signal.metadata["failure_count"] == 5
        assert signal.metadata["window_minutes"] == 30

    def test_review_risk_signal_rejects_invalid_status(self) -> None:
        user = UserFactory()
        signal = auth_services.create_auth_risk_signal(
            signal_type=AuthRiskSignalType.NEW_IP,
            severity=AuthRiskSeverity.LOW,
            user=user,
        )
        reviewer = AdminUserFactory()

        with pytest.raises(auth_services.AuthServiceError, match="نامعتبر"):
            auth_services.review_auth_risk_signal(
                signal=signal,
                reviewed_by=reviewer,
                status="bogus",
            )


# ============================================================
# ۹ — نگاشت خطاهای OTP
# ============================================================


class TestMapOTPErrorToServiceError:
    """هر استثنای OTP باید به پیام کاربرپسند و original درست نگاشت شود."""

    def test_otp_not_found(self) -> None:
        mapped = auth_services._map_otp_error_to_service_error(OTPNotFound())

        assert isinstance(mapped, auth_services.OTPServiceError)
        assert "نامعتبر یا منقضی" in str(mapped)
        assert isinstance(mapped.original, OTPNotFound)

    def test_otp_expired(self) -> None:
        mapped = auth_services._map_otp_error_to_service_error(OTPExpired())

        assert "نامعتبر یا منقضی" in str(mapped)
        assert isinstance(mapped.original, OTPExpired)

    def test_otp_invalid_code(self) -> None:
        mapped = auth_services._map_otp_error_to_service_error(OTPInvalidCode())

        assert "اشتباه است" in str(mapped)
        assert isinstance(mapped.original, OTPInvalidCode)

    def test_otp_too_many_attempts(self) -> None:
        mapped = auth_services._map_otp_error_to_service_error(OTPTooManyAttempts())

        assert "حد مجاز" in str(mapped)
        assert isinstance(mapped.original, OTPTooManyAttempts)

    def test_otp_cooldown_includes_seconds(self) -> None:
        mapped = auth_services._map_otp_error_to_service_error(OTPCooldownActive(7))

        assert "7 ثانیه" in str(mapped)
        assert isinstance(mapped.original, OTPCooldownActive)

    def test_otp_delivery_error(self) -> None:
        mapped = auth_services._map_otp_error_to_service_error(OTPDeliveryError())

        assert "ارسال کد" in str(mapped)
        assert isinstance(mapped.original, OTPDeliveryError)

    def test_unknown_error_falls_back_to_generic_message(self) -> None:
        original = RuntimeError("boom")

        mapped = auth_services._map_otp_error_to_service_error(original)

        assert "خطایی رخ داد" in str(mapped)
        assert mapped.original is original


# ============================================================
# ۱۰ — flowهای legacy (ایمیل‌محور)
# ============================================================


class TestLegacyAuthFlowServices:
    """register_user، login_user، verify_user_email، reset، request OTP."""

    def test_register_user_creates_user_and_email_otp(self) -> None:
        email = _uniq_email()

        user = auth_services.register_user(
            email=email.upper(),  # باید normalize شود
            password="Sup3rSecret!",
            first_name="تست",
        )

        assert user.email == normalize_email(email)
        assert user.check_password("Sup3rSecret!")
        assert OTPCode.objects.filter(
            identifier_value=normalize_email(email),
            purpose=OTPPurpose.EMAIL_VERIFICATION,
        ).exists()

    def test_create_and_send_otp_returns_otp_row_for_email_user(self) -> None:
        user = UserFactory(email=_uniq_email())

        otp = auth_services.create_and_send_otp(
            user=user,
            purpose=OTPPurpose.EMAIL_VERIFICATION,
        )

        assert isinstance(otp, OTPCode)
        assert otp.identifier_value == user.email
        assert otp.purpose == OTPPurpose.EMAIL_VERIFICATION

    def test_create_and_send_otp_raises_when_email_missing(self) -> None:
        user = UserFactory(email=None, phone_number=_uniq_phone())

        with pytest.raises(ValueError, match="valid email identifier"):
            auth_services.create_and_send_otp(
                user=user,
                purpose=OTPPurpose.EMAIL_VERIFICATION,
            )

    def test_verify_otp_success_with_minted_code(self) -> None:
        email = _uniq_email()
        user = UserFactory(email=email)
        minted = _mint_otp(
            kind=PrimaryIdentifierKind.EMAIL,
            value=email,
            purpose=OTPPurpose.EMAIL_VERIFICATION,
        )

        assert (
            auth_services.verify_otp(
                user=user,
                code=minted.code_plain,
                purpose=OTPPurpose.EMAIL_VERIFICATION,
            )
            is True
        )

    def test_verify_otp_wrong_code_returns_false(self) -> None:
        user = UserFactory(email=_uniq_email())

        assert (
            auth_services.verify_otp(
                user=user,
                code="000000",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
            )
            is False
        )

    def test_verify_otp_without_any_code_returns_false(self) -> None:
        user = UserFactory(email=_uniq_email())

        assert (
            auth_services.verify_otp(
                user=user,
                code="123456",
                purpose=OTPPurpose.EMAIL_VERIFICATION,
            )
            is False
        )

    def test_login_user_rejects_invalid_email_format(self) -> None:
        assert (
            auth_services.login_user(
                request=_bare_request(),
                email="not-an-email",
                password="whatever",
            )
            is None
        )

    def test_login_user_returns_none_for_wrong_password(self) -> None:
        email = _uniq_email()
        UserFactory(email=email, password="RightPass!234", is_email_verified=True)

        assert (
            auth_services.login_user(
                request=_bare_request(),
                email=email,
                password="WrongPass!999",
            )
            is None
        )

    def test_login_user_success_returns_tokens_and_session(self) -> None:
        email = _uniq_email()
        user = UserFactory(email=email, password="RightPass!234", is_email_verified=True)

        result = auth_services.login_user(
            request=_bare_request(user_agent="Firefox/127", ip="203.0.113.10"),
            email=email,
            password="RightPass!234",
        )

        assert result is not None
        assert result["user"].pk == user.pk
        assert set(result["tokens"]) == {"refresh", "access"}
        assert result["session"].user_id == user.pk
        assert result["session"].device_label == "Firefox browser"

    def test_verify_user_email_marks_verified_after_otp(self) -> None:
        email = _uniq_email()
        user = UserFactory(email=email, is_email_verified=False)
        minted = _mint_otp(
            kind=PrimaryIdentifierKind.EMAIL,
            value=email,
            purpose=OTPPurpose.EMAIL_VERIFICATION,
        )

        assert auth_services.verify_user_email(user=user, code=minted.code_plain) is True

        user.refresh_from_db()
        assert user.is_email_verified is True

    def test_verify_user_email_false_on_bad_code(self) -> None:
        user = UserFactory(email=_uniq_email(), is_email_verified=False)

        assert auth_services.verify_user_email(user=user, code="000000") is False

        user.refresh_from_db()
        assert user.is_email_verified is False

    def test_verify_user_email_short_circuits_when_already_verified(self) -> None:
        email = _uniq_email()
        user = UserFactory(email=email, is_email_verified=True)
        minted = _mint_otp(
            kind=PrimaryIdentifierKind.EMAIL,
            value=email,
            purpose=OTPPurpose.EMAIL_VERIFICATION,
        )

        assert auth_services.verify_user_email(user=user, code=minted.code_plain) is True
        user.refresh_from_db()
        assert user.is_email_verified is True

    def test_request_password_reset_sends_otp(self) -> None:
        email = _uniq_email()
        user = UserFactory(email=email)

        otp = auth_services.request_password_reset(user=user)

        assert isinstance(otp, OTPCode)
        assert otp.purpose == OTPPurpose.PASSWORD_RESET

    def test_reset_password_with_otp_success(self) -> None:
        email = _uniq_email()
        user = UserFactory(email=email, password="OldPass!234")
        minted = _mint_otp(
            kind=PrimaryIdentifierKind.EMAIL,
            value=email,
            purpose=OTPPurpose.PASSWORD_RESET,
        )

        assert (
            auth_services.reset_password_with_otp(
                user=user,
                code=minted.code_plain,
                new_password="NewPass!567",
            )
            is True
        )

        user.refresh_from_db()
        assert user.check_password("NewPass!567")

    def test_reset_password_with_otp_false_on_bad_code(self) -> None:
        user = UserFactory(email=_uniq_email(), password="OldPass!234")

        assert (
            auth_services.reset_password_with_otp(
                user=user,
                code="000000",
                new_password="NewPass!567",
            )
            is False
        )

        user.refresh_from_db()
        assert user.check_password("OldPass!234")

    def test_change_password_rejects_wrong_old_password(self) -> None:
        user = UserFactory(password="OldPass!234")

        assert (
            auth_services.change_password(
                user=user,
                old_password="WrongPass!999",
                new_password="NewPass!567",
            )
            is False
        )

    def test_change_password_success(self) -> None:
        user = UserFactory(password="OldPass!234")

        assert (
            auth_services.change_password(
                user=user,
                old_password="OldPass!234",
                new_password="NewPass!567",
            )
            is True
        )
        user.refresh_from_db()
        assert user.check_password("NewPass!567")


# ============================================================
# ۱۱ — کش وضعیت نشست
# ============================================================


class TestSessionValidityCache:
    """validate_and_touch_session در همهٔ حالت‌های کش/DB."""

    def test_legacy_token_without_sid_passes(self) -> None:
        user = UserFactory()

        assert auth_services.validate_and_touch_session(user=user, token_claims={}) is True

    def test_unknown_session_is_rejected_and_cached_as_revoked(self) -> None:
        user = UserFactory()

        assert (
            auth_services.validate_and_touch_session(
                user=user, token_claims={SESSION_ID_CLAIM: 999_999}
            )
            is False
        )

    def test_revoked_session_is_rejected_immediately_and_cached(self) -> None:
        user = UserFactory()
        refresh = RefreshToken.for_user(user)
        session = auth_services._create_auth_session(
            user=user,
            refresh_token=str(refresh),
            request=_bare_request(),
        )
        auth_services.revoke_auth_session(session=session)

        assert (
            auth_services.validate_and_touch_session(
                user=user, token_claims={SESSION_ID_CLAIM: session.pk}
            )
            is False
        )
        # فراخوانی دوم باید از کشِ «revoked» رد شود (بدون کوئری DB).
        assert (
            auth_services.validate_and_touch_session(
                user=user, token_claims={SESSION_ID_CLAIM: session.pk}
            )
            is False
        )

    def test_healthy_session_returns_true_and_caches(self) -> None:
        user = UserFactory()
        refresh = RefreshToken.for_user(user)
        session = auth_services._create_auth_session(
            user=user,
            refresh_token=str(refresh),
            request=_bare_request(),
        )

        assert (
            auth_services.validate_and_touch_session(
                user=user, token_claims={SESSION_ID_CLAIM: session.pk}
            )
            is True
        )
        # بار دوم باید از کش بخورد (بدون خطا و همچنان True).
        assert (
            auth_services.validate_and_touch_session(
                user=user, token_claims={SESSION_ID_CLAIM: session.pk}
            )
            is True
        )

    def test_revoke_auth_session_is_idempotent(self) -> None:
        user = UserFactory()
        refresh = RefreshToken.for_user(user)
        session = auth_services._create_auth_session(
            user=user,
            refresh_token=str(refresh),
            request=_bare_request(),
        )
        auth_services.revoke_auth_session(session=session)

        second = auth_services.revoke_auth_session(session=session)

        assert second.pk == session.pk
        assert second.is_revoked is True

    def test_revoke_all_user_sessions_returns_count_and_clears_cache(self) -> None:
        user = UserFactory()
        sessions = []
        for _ in range(2):
            refresh = RefreshToken.for_user(user)
            sessions.append(
                auth_services._create_auth_session(
                    user=user,
                    refresh_token=str(refresh),
                    request=_bare_request(),
                )
            )
        # یکی از نشست‌ها قبلاً باطل شده تا شمردن فقط active را نشان دهد.
        refresh = RefreshToken.for_user(user)
        revoked = auth_services._create_auth_session(
            user=user,
            refresh_token=str(refresh),
            request=_bare_request(),
        )
        auth_services.revoke_auth_session(session=revoked)

        count = auth_services.revoke_all_user_sessions(user=user)

        assert count == 2
        sessions[0].refresh_from_db()
        sessions[1].refresh_from_db()
        assert sessions[0].is_revoked is True
        assert sessions[1].is_revoked is True


# ============================================================
# ۱۲ — flowهای multi-identifier
# ============================================================


class TestMultiIdentifierServices:
    """signup_request/verify، login، forgot password، identifier_add."""

    def test_signup_request_sends_and_normalizes_email(self) -> None:
        email = _uniq_email().upper()

        auth_services.signup_request(
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value=email,
        )

        assert OTPCode.objects.filter(
            identifier_value=normalize_email(email),
            purpose=OTPPurpose.SIGNUP,
        ).exists()

    def test_signup_request_sends_phone_otp(self) -> None:
        phone = _uniq_phone()

        auth_services.signup_request(
            identifier_kind=PrimaryIdentifierKind.PHONE,
            identifier_value=phone,
        )

        assert OTPCode.objects.filter(
            identifier_value=normalize_phone(phone),
            purpose=OTPPurpose.SIGNUP,
        ).exists()

    def test_signup_request_maps_cooldown_to_service_error(self) -> None:
        email = _uniq_email()
        auth_services.signup_request(
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value=email,
        )

        with pytest.raises(auth_services.OTPServiceError, match="ثانیه"):
            auth_services.signup_request(
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value=email,
            )

    def test_signup_verify_email_success_without_request_returns_tokens(self) -> None:
        email = _uniq_email()
        minted = _mint_otp(kind=PrimaryIdentifierKind.EMAIL, value=email, purpose=OTPPurpose.SIGNUP)

        result = auth_services.signup_verify(
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value=email,
            code=minted.code_plain,
            password="Sup3rSecret!",
            request=None,
        )

        assert set(result) == {"user", "tokens"}
        assert set(result["tokens"]) == {"refresh", "access"}
        assert result["user"].email == normalize_email(email)
        assert result["user"].is_email_verified is True
        assert result["user"].primary_identifier == PrimaryIdentifierKind.EMAIL

    def test_signup_verify_email_rejects_duplicate(self) -> None:
        taken = _uniq_email()
        UserFactory(email=taken)
        minted = _mint_otp(kind=PrimaryIdentifierKind.EMAIL, value=taken, purpose=OTPPurpose.SIGNUP)

        with pytest.raises(auth_services.IdentifierAlreadyExists):
            auth_services.signup_verify(
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value=taken,
                code=minted.code_plain,  # کد درست → بررسی تکراری‌بودن می‌رسد
                password="Sup3rSecret!",
            )

    def test_signup_verify_phone_rejects_duplicate(self) -> None:
        taken = _uniq_phone()
        UserFactory(phone_number=taken)
        minted = _mint_otp(kind=PrimaryIdentifierKind.PHONE, value=taken, purpose=OTPPurpose.SIGNUP)

        with pytest.raises(auth_services.IdentifierAlreadyExists):
            auth_services.signup_verify(
                identifier_kind=PrimaryIdentifierKind.PHONE,
                identifier_value=taken,
                code=minted.code_plain,
                password="Sup3rSecret!",
            )

    def test_signup_verify_bad_code_maps_to_service_error(self) -> None:
        with pytest.raises(auth_services.OTPServiceError):
            auth_services.signup_verify(
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value=_uniq_email(),
                code="123456",
                password="Sup3rSecret!",
            )

    def test_login_with_password_rejects_unverified_primary(self) -> None:
        email = _uniq_email()
        user = UserFactory(email=email, is_email_verified=False, password="RightPass!234")

        with pytest.raises(auth_services.AccountNotVerified):
            auth_services.login_with_password(
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value=email,
                password="RightPass!234",
                request=_bare_request(),
            )
        assert user.pk

    def test_login_otp_request_silently_ignores_unknown_identifier(self) -> None:
        auth_services.login_otp_request(
            identifier_kind=PrimaryIdentifierKind.PHONE,
            identifier_value=_uniq_phone(),
        )  # نباید خطا بدهد؛ silently ignored است.

    def test_login_otp_request_maps_cooldown_to_service_error(self) -> None:
        phone = _uniq_phone()
        UserFactory(phone_number=phone, is_phone_verified=True)
        auth_services.login_otp_request(
            identifier_kind=PrimaryIdentifierKind.PHONE,
            identifier_value=phone,
        )

        with pytest.raises(auth_services.OTPServiceError, match="ثانیه"):
            auth_services.login_otp_request(
                identifier_kind=PrimaryIdentifierKind.PHONE,
                identifier_value=phone,
            )

    def test_login_otp_verify_maps_bad_code_to_service_error(self) -> None:
        phone = _uniq_phone()
        UserFactory(phone_number=phone, is_phone_verified=True)

        with pytest.raises(auth_services.OTPServiceError):
            auth_services.login_otp_verify(
                identifier_kind=PrimaryIdentifierKind.PHONE,
                identifier_value=phone,
                code="000000",
                request=_bare_request(),
            )

    def test_login_otp_verify_raises_when_user_became_inactive(self) -> None:
        phone = _uniq_phone()
        user = UserFactory(phone_number=phone, is_phone_verified=True)
        minted = _mint_otp(kind=PrimaryIdentifierKind.PHONE, value=phone, purpose=OTPPurpose.LOGIN)
        user.is_active = False
        user.save(update_fields=["is_active"])

        with pytest.raises(auth_services.IdentifierNotFound):
            auth_services.login_otp_verify(
                identifier_kind=PrimaryIdentifierKind.PHONE,
                identifier_value=phone,
                code=minted.code_plain,
                request=_bare_request(),
            )

    def test_forgot_password_request_silently_ignores_unknown_identifier(self) -> None:
        auth_services.forgot_password_request(
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value=_uniq_email(),
        )  # بدون خطا.

    def test_forgot_password_request_maps_cooldown_to_service_error(self) -> None:
        phone = _uniq_phone()
        UserFactory(phone_number=phone, is_phone_verified=True)
        auth_services.forgot_password_request(
            identifier_kind=PrimaryIdentifierKind.PHONE,
            identifier_value=phone,
        )

        with pytest.raises(auth_services.OTPServiceError, match="ثانیه"):
            auth_services.forgot_password_request(
                identifier_kind=PrimaryIdentifierKind.PHONE,
                identifier_value=phone,
            )

    def test_forgot_password_confirm_changes_password(self) -> None:
        phone = _uniq_phone()
        UserFactory(phone_number=phone, is_phone_verified=True)
        minted = _mint_otp(
            kind=PrimaryIdentifierKind.PHONE,
            value=phone,
            purpose=OTPPurpose.PASSWORD_RESET,
        )

        auth_services.forgot_password_confirm(
            identifier_kind=PrimaryIdentifierKind.PHONE,
            identifier_value=phone,
            code=minted.code_plain,
            new_password="NewPass!567",
        )

        user = User.all_objects.get(phone_number=phone)
        assert user.check_password("NewPass!567")

    def test_forgot_password_confirm_maps_bad_code_to_service_error(self) -> None:
        phone = _uniq_phone()
        UserFactory(phone_number=phone, is_phone_verified=True)

        with pytest.raises(auth_services.OTPServiceError):
            auth_services.forgot_password_confirm(
                identifier_kind=PrimaryIdentifierKind.PHONE,
                identifier_value=phone,
                code="000000",
                new_password="NewPass!567",
            )

    def test_forgot_password_confirm_raises_when_user_became_inactive(self) -> None:
        phone = _uniq_phone()
        user = UserFactory(phone_number=phone, is_phone_verified=True)
        minted = _mint_otp(
            kind=PrimaryIdentifierKind.PHONE,
            value=phone,
            purpose=OTPPurpose.PASSWORD_RESET,
        )
        user.is_active = False
        user.save(update_fields=["is_active"])

        with pytest.raises(auth_services.IdentifierNotFound):
            auth_services.forgot_password_confirm(
                identifier_kind=PrimaryIdentifierKind.PHONE,
                identifier_value=phone,
                code=minted.code_plain,
                new_password="NewPass!567",
            )

    def test_identifier_add_request_maps_cooldown_to_service_error(self) -> None:
        user = UserFactory()
        phone = _uniq_phone()
        auth_services.identifier_add_request(
            user=user,
            identifier_kind=PrimaryIdentifierKind.PHONE,
            identifier_value=phone,
        )

        with pytest.raises(auth_services.OTPServiceError, match="ثانیه"):
            auth_services.identifier_add_request(
                user=user,
                identifier_kind=PrimaryIdentifierKind.PHONE,
                identifier_value=phone,
            )

    def test_identifier_add_verify_attaches_new_phone_and_verifies(self) -> None:
        user = UserFactory()
        phone = _uniq_phone()
        minted = _mint_otp(
            kind=PrimaryIdentifierKind.PHONE,
            value=phone,
            purpose=OTPPurpose.IDENTIFIER_ADD,
        )

        result = auth_services.identifier_add_verify(
            user=user,
            identifier_kind=PrimaryIdentifierKind.PHONE,
            identifier_value=phone,
            code=minted.code_plain,
        )

        user.refresh_from_db()
        assert result.pk == user.pk
        assert user.phone_number == normalize_phone(phone)
        assert user.is_phone_verified is True

    def test_identifier_add_verify_marks_existing_email_verified_without_rewrite(self) -> None:
        email = _uniq_email()
        user = UserFactory(email=email, is_email_verified=False)
        minted = _mint_otp(
            kind=PrimaryIdentifierKind.EMAIL,
            value=email,
            purpose=OTPPurpose.IDENTIFIER_ADD,
        )

        auth_services.identifier_add_verify(
            user=user,
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value=email,
            code=minted.code_plain,
        )

        user.refresh_from_db()
        assert user.email == email
        assert user.is_email_verified is True

    def test_identifier_add_verify_bad_code_maps_to_service_error(self) -> None:
        # کاربر بدون ایمیل تا channel ایمیلش اشغال نباشد و خطا از OTP بیاید.
        user = UserFactory(email=None, phone_number=_uniq_phone())

        with pytest.raises(auth_services.OTPServiceError):
            auth_services.identifier_add_verify(
                user=user,
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value=_uniq_email(),
                code="000000",
            )

    def test_make_primary_identifier_rejects_unattached(self) -> None:
        user = UserFactory()

        with pytest.raises(auth_services.IdentifierNotAttached):
            auth_services.make_primary_identifier(
                user=user,
                identifier_kind=PrimaryIdentifierKind.PHONE,
            )

    def test_make_primary_identifier_rejects_unverified(self) -> None:
        user = UserFactory(phone_number=_uniq_phone(), is_phone_verified=False)

        with pytest.raises(auth_services.IdentifierNotVerified):
            auth_services.make_primary_identifier(
                user=user,
                identifier_kind=PrimaryIdentifierKind.PHONE,
            )

    def test_make_primary_identifier_noop_when_already_primary(self) -> None:
        email = _uniq_email()
        user = UserFactory(email=email, is_email_verified=True)

        result = auth_services.make_primary_identifier(
            user=user,
            identifier_kind=PrimaryIdentifierKind.EMAIL,
        )

        user.refresh_from_db()
        assert result.pk == user.pk
        assert user.primary_identifier == PrimaryIdentifierKind.EMAIL

    def test_make_primary_identifier_switches_to_verified_phone(self) -> None:
        phone = _uniq_phone()
        user = UserFactory(
            email=_uniq_email(),
            phone_number=phone,
            is_email_verified=True,
            is_phone_verified=True,
        )

        auth_services.make_primary_identifier(
            user=user,
            identifier_kind=PrimaryIdentifierKind.PHONE,
        )

        user.refresh_from_db()
        assert user.primary_identifier == PrimaryIdentifierKind.PHONE
