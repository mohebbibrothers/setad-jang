"""
DRF serializers for authentication, profile, and user management APIs.
"""

from __future__ import annotations

from typing import Final

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .choices import AuthRiskStatus, Gender, UserRole
from .constants import SESSION_ID_CLAIM, SESSION_REVOKED_MESSAGE
from .models import AuthRiskSignal, AuthSession, PrimaryIdentifierKind, Profile, User
from .normalizers import normalize_email, normalize_identifier, normalize_phone
from .validators import validate_email_for_signup, validate_phone_format

# ============================================================
# Constants
# ============================================================

OTP_CODE_LENGTH: Final[int] = 5
IDENTIFIER_MAX_LENGTH: Final[int] = 254

# ============================================================
# Internal helpers
# ============================================================


def _build_drf_validation_error(
    exc: DjangoValidationError,
) -> serializers.ValidationError:
    """
    Convert Django ValidationError to DRF ValidationError.
    """
    messages = getattr(exc, "messages", None)
    if messages:
        return serializers.ValidationError(messages)

    return serializers.ValidationError(str(exc))


def _identifier_exists(
    *,
    identifier_kind: str,
    identifier_value: str,
    exclude_user_id: int | None = None,
) -> bool:
    """
    Check whether an identifier is already used by another user.
    """
    queryset = User.all_objects.all()

    if identifier_kind == PrimaryIdentifierKind.EMAIL:
        queryset = queryset.filter(email__iexact=identifier_value)
    elif identifier_kind == PrimaryIdentifierKind.PHONE:
        queryset = queryset.filter(phone_number=identifier_value)
    else:
        raise serializers.ValidationError("نوع شناسه نامعتبر است.")

    if exclude_user_id is not None:
        queryset = queryset.exclude(pk=exclude_user_id)

    return queryset.exists()


def _normalize_identifier_for_auth(value: str) -> tuple[str, str]:
    """
    Normalize identifier for auth flows that should not leak existence.
    """
    try:
        return normalize_identifier(value)
    except DjangoValidationError as exc:
        raise _build_drf_validation_error(exc) from exc


def _normalize_identifier_for_signup(value: str) -> tuple[str, str]:
    """
    Normalize + validate identifier for signup flows.

    Rules:
    - email -> normalized + disposable/MX validation
    - phone -> normalized + phone validation hook
    - identifier must not already exist
    """
    identifier_kind, identifier_value = _normalize_identifier_for_auth(value)

    if identifier_kind == PrimaryIdentifierKind.EMAIL:
        try:
            validate_email_for_signup(identifier_value)
        except DjangoValidationError as exc:
            raise _build_drf_validation_error(exc) from exc
    elif identifier_kind == PrimaryIdentifierKind.PHONE:
        try:
            validate_phone_format(identifier_value)
        except DjangoValidationError as exc:
            raise _build_drf_validation_error(exc) from exc

    if _identifier_exists(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
    ):
        raise serializers.ValidationError("این شناسه قبلاً ثبت شده است.")

    return identifier_kind, identifier_value


def _get_request_user_from_context(serializer: serializers.Serializer) -> User:
    """
    Extract authenticated user from serializer context.

    این helper فقط در serializerهای identifier-management استفاده می‌شود.
    """
    request = serializer.context.get("request")
    user = getattr(request, "user", None)

    if user is None or not getattr(user, "is_authenticated", False):
        raise serializers.ValidationError("کاربر احراز هویت نشده است.")

    return user


def _get_user_identifier_state(
    *,
    user: User,
    identifier_kind: str,
) -> tuple[str | None, bool]:
    """
    Return current value + verified state for a given identifier kind on the user.
    """
    if identifier_kind == PrimaryIdentifierKind.EMAIL:
        return user.email, user.is_email_verified

    if identifier_kind == PrimaryIdentifierKind.PHONE:
        return user.phone_number, user.is_phone_verified

    raise serializers.ValidationError("نوع شناسه نامعتبر است.")


def _normalize_identifier_for_identifier_add(
    *,
    user: User,
    value: str,
) -> tuple[str, str]:
    """
    Normalize + validate identifier for authenticated add/verify flows.

    Supported cases:
    1. user has no identifier of this kind yet                -> allowed
    2. user already has the exact same identifier unverified  -> allowed
    3. user already has the exact same identifier verified    -> rejected
    4. user already has another value in same channel         -> rejected
    5. identifier belongs to another user                     -> rejected

    Note:
    "replace identifier" intentionally is NOT supported in this phase.
    That must be implemented via a dedicated explicit endpoint/flow.
    """
    identifier_kind, identifier_value = _normalize_identifier_for_auth(value)

    if identifier_kind == PrimaryIdentifierKind.EMAIL:
        try:
            validate_email_for_signup(identifier_value)
        except DjangoValidationError as exc:
            raise _build_drf_validation_error(exc) from exc
    elif identifier_kind == PrimaryIdentifierKind.PHONE:
        try:
            validate_phone_format(identifier_value)
        except DjangoValidationError as exc:
            raise _build_drf_validation_error(exc) from exc

    current_value, current_verified = _get_user_identifier_state(
        user=user,
        identifier_kind=identifier_kind,
    )

    if current_value is not None:
        if current_value == identifier_value:
            if current_verified:
                raise serializers.ValidationError(
                    "این شناسه قبلاً برای حساب شما تأیید شده است.",
                )
            return identifier_kind, identifier_value

        if identifier_kind == PrimaryIdentifierKind.EMAIL:
            raise serializers.ValidationError(
                "برای این حساب قبلاً یک ایمیل ثبت شده است. "
                "جایگزینی ایمیل در این endpoint پشتیبانی نمی‌شود.",
            )

        raise serializers.ValidationError(
            "برای این حساب قبلاً یک شماره موبایل ثبت شده است. "
            "جایگزینی شماره موبایل در این endpoint پشتیبانی نمی‌شود.",
        )

    if _identifier_exists(
        identifier_kind=identifier_kind,
        identifier_value=identifier_value,
        exclude_user_id=user.pk,
    ):
        raise serializers.ValidationError("این شناسه قبلاً ثبت شده است.")

    return identifier_kind, identifier_value


# ============================================================
# User Serializers
# ============================================================


class ProfileSerializer(serializers.ModelSerializer):
    """ProfileSerializer implementation for the authentication application."""

    phone_number = serializers.CharField(
        source="user.phone_number",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Profile
        fields = (
            "phone_number",
            "national_code",
            "birth_date",
            "gender",
            "avatar",
            "bio",
            "province",
            "city",
            "address",
        )


class UserMeSerializer(serializers.ModelSerializer):
    """UserMeSerializer implementation for the authentication application."""

    profile = ProfileSerializer(read_only=True)
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "is_email_verified",
            "date_joined",
            "profile",
        )
        read_only_fields = (
            "id",
            "email",
            "role",
            "is_email_verified",
            "date_joined",
        )


class UserAdminSerializer(serializers.ModelSerializer):
    """UserAdminSerializer implementation for the authentication application."""

    profile = ProfileSerializer(read_only=True)
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "is_active",
            "is_email_verified",
            "is_staff",
            "date_joined",
            "last_login",
            "last_login_ip",
            "profile",
        )
        read_only_fields = ("id", "date_joined", "last_login", "last_login_ip")


# ============================================================
# Legacy Auth Input Serializers — kept for auth v1 compatibility
# ============================================================


class RegisterSerializer(serializers.Serializer):
    """RegisterSerializer implementation for the authentication application."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=100)

    def validate_email(self, value: str) -> str:
        try:
            normalized_email = normalize_email(value)
        except DjangoValidationError as exc:
            raise _build_drf_validation_error(exc) from exc

        if User.all_objects.filter(email__iexact=normalized_email).exists():
            raise serializers.ValidationError("این ایمیل قبلاً ثبت شده است.")

        return normalized_email


class LoginSerializer(serializers.Serializer):
    """LoginSerializer implementation for the authentication application."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_email(self, value: str) -> str:
        try:
            return normalize_email(value)
        except DjangoValidationError as exc:
            raise _build_drf_validation_error(exc) from exc


class VerifyEmailSerializer(serializers.Serializer):
    """VerifyEmailSerializer implementation for the authentication application."""

    email = serializers.EmailField()
    code = serializers.CharField(min_length=OTP_CODE_LENGTH, max_length=OTP_CODE_LENGTH)

    def validate_email(self, value: str) -> str:
        try:
            return normalize_email(value)
        except DjangoValidationError as exc:
            raise _build_drf_validation_error(exc) from exc


class ResendVerificationSerializer(serializers.Serializer):
    """ResendVerificationSerializer implementation for the authentication application."""

    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        try:
            return normalize_email(value)
        except DjangoValidationError as exc:
            raise _build_drf_validation_error(exc) from exc


class RefreshTokenInputSerializer(serializers.Serializer):
    """RefreshTokenInputSerializer implementation for the authentication application."""

    refresh = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    """LogoutSerializer implementation for the authentication application."""

    refresh = serializers.CharField()


class ForgotPasswordSerializer(serializers.Serializer):
    """ForgotPasswordSerializer implementation for the authentication application."""

    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        try:
            return normalize_email(value)
        except DjangoValidationError as exc:
            raise _build_drf_validation_error(exc) from exc


class ResetPasswordSerializer(serializers.Serializer):
    """ResetPasswordSerializer implementation for the authentication application."""

    email = serializers.EmailField()
    code = serializers.CharField(min_length=OTP_CODE_LENGTH, max_length=OTP_CODE_LENGTH)
    new_password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
    )

    def validate_email(self, value: str) -> str:
        try:
            return normalize_email(value)
        except DjangoValidationError as exc:
            raise _build_drf_validation_error(exc) from exc


class ChangePasswordSerializer(serializers.Serializer):
    """ChangePasswordSerializer implementation for the authentication application."""

    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
    )


# ============================================================
# Phase H — Multi-Identifier Public Auth Serializers
# ============================================================


class BaseIdentifierSerializer(serializers.Serializer):
    """
    Base serializer for identifier-based auth flows.

    Output contract after validation:
    - identifier: normalized identifier value
    - identifier_kind: "email" | "phone"
    """

    identifier = serializers.CharField(max_length=IDENTIFIER_MAX_LENGTH)

    def normalize_identifier_value(self, value: str) -> tuple[str, str]:
        return _normalize_identifier_for_auth(value)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        attrs = super().validate(attrs)

        identifier_kind, identifier_value = self.normalize_identifier_value(
            str(attrs["identifier"]),
        )
        attrs["identifier"] = identifier_value
        attrs["identifier_kind"] = identifier_kind

        return attrs


class SignupRequestSerializer(BaseIdentifierSerializer):
    """
    Step 1 of signup:
    request OTP for a new identifier.
    """

    def normalize_identifier_value(self, value: str) -> tuple[str, str]:
        return _normalize_identifier_for_signup(value)


class SignupVerifySerializer(BaseIdentifierSerializer):
    """
    Step 2 of signup:
    verify OTP and create account with password.
    """

    code = serializers.CharField(min_length=OTP_CODE_LENGTH, max_length=OTP_CODE_LENGTH)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=100)

    def normalize_identifier_value(self, value: str) -> tuple[str, str]:
        return _normalize_identifier_for_signup(value)


class LoginPasswordSerializer(BaseIdentifierSerializer):
    """
    Password-based login with either email or phone number.
    """

    password = serializers.CharField(write_only=True)


class OTPLoginRequestSerializer(BaseIdentifierSerializer):
    """
    Request login OTP for an existing identifier.
    """


class OTPLoginVerifySerializer(BaseIdentifierSerializer):
    """
    Verify login OTP and issue JWT tokens.
    """

    code = serializers.CharField(min_length=OTP_CODE_LENGTH, max_length=OTP_CODE_LENGTH)


class IdentifierForgotPasswordRequestSerializer(BaseIdentifierSerializer):
    """
    Request password reset OTP by identifier.
    """


class IdentifierForgotPasswordConfirmSerializer(BaseIdentifierSerializer):
    """
    Confirm password reset by identifier + OTP + new password.
    """

    code = serializers.CharField(min_length=OTP_CODE_LENGTH, max_length=OTP_CODE_LENGTH)
    new_password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
    )


# ============================================================
# Phase H.2 — Authenticated Identifier Management Serializers
# ============================================================


class BaseAuthenticatedIdentifierSerializer(BaseIdentifierSerializer):
    """
    Base serializer for authenticated identifier-management flows.
    """

    def normalize_identifier_value(self, value: str) -> tuple[str, str]:
        user = _get_request_user_from_context(self)
        return _normalize_identifier_for_identifier_add(
            user=user,
            value=value,
        )


class IdentifierAddRequestSerializer(BaseAuthenticatedIdentifierSerializer):
    """
    Request OTP for attaching or verifying a secondary identifier.

    Supported:
    - add a missing secondary identifier
    - re-verify the same attached but unverified identifier

    Not supported:
    - replacing an existing identifier in the same channel
    """


class IdentifierAddVerifySerializer(BaseAuthenticatedIdentifierSerializer):
    """
    Verify OTP for attaching or verifying a secondary identifier.
    """

    code = serializers.CharField(min_length=OTP_CODE_LENGTH, max_length=OTP_CODE_LENGTH)


class IdentifierMakePrimarySerializer(serializers.Serializer):
    """
    Switch primary identifier to an already attached + verified channel.
    """

    identifier_kind = serializers.ChoiceField(choices=PrimaryIdentifierKind.choices)

    def validate_identifier_kind(self, value: str) -> str:
        user = _get_request_user_from_context(self)

        if value == PrimaryIdentifierKind.EMAIL:
            if not user.email:
                raise serializers.ValidationError(
                    "هیچ ایمیلی برای این حساب ثبت نشده است.",
                )
            if not user.is_email_verified:
                raise serializers.ValidationError(
                    "ایمیل این حساب هنوز تأیید نشده است.",
                )
            return value

        if value == PrimaryIdentifierKind.PHONE:
            if not user.phone_number:
                raise serializers.ValidationError(
                    "هیچ شماره موبایلی برای این حساب ثبت نشده است.",
                )
            if not user.is_phone_verified:
                raise serializers.ValidationError(
                    "شماره موبایل این حساب هنوز تأیید نشده است.",
                )
            return value

        raise serializers.ValidationError("نوع شناسه نامعتبر است.")


# ============================================================
# Update Serializers
# ============================================================


class UpdateMeSerializer(serializers.Serializer):
    """UpdateMeSerializer implementation for the authentication application."""

    first_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=100)


class UpdateProfileSerializer(serializers.Serializer):
    """UpdateProfileSerializer implementation for the authentication application."""

    phone_number = serializers.CharField(required=False, allow_blank=True, max_length=20)
    national_code = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=10,
    )
    birth_date = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(
        required=False,
        choices=Gender.choices,
        allow_blank=True,
    )
    avatar = serializers.ImageField(required=False, allow_null=True)
    bio = serializers.CharField(required=False, allow_blank=True)
    province = serializers.CharField(required=False, allow_blank=True, max_length=100)
    city = serializers.CharField(required=False, allow_blank=True, max_length=100)
    address = serializers.CharField(required=False, allow_blank=True)

    def validate_phone_number(self, value: str) -> str:
        if value == "":
            return value

        try:
            return normalize_phone(value)
        except DjangoValidationError as exc:
            raise _build_drf_validation_error(exc) from exc


# ============================================================
# Admin Serializers
# ============================================================


class AdminUserUpdateSerializer(serializers.Serializer):
    """AdminUserUpdateSerializer implementation for the authentication application."""

    first_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    is_active = serializers.BooleanField(required=False)
    is_email_verified = serializers.BooleanField(required=False)


class AdminChangeRoleSerializer(serializers.Serializer):
    """AdminChangeRoleSerializer implementation for the authentication application."""

    role = serializers.ChoiceField(choices=UserRole.choices)


# ============================================================
# Auth Session Serializers
# ============================================================


class AuthSessionSerializer(serializers.ModelSerializer):
    """Read serializer for tracked user auth sessions/devices."""

    revoked_by_email = serializers.EmailField(
        source="revoked_by.email", read_only=True, allow_null=True
    )
    is_current = serializers.SerializerMethodField()

    class Meta:
        model = AuthSession
        fields = (
            "id",
            "device_label",
            "ip_address",
            "user_agent",
            "request_id",
            "is_revoked",
            "revoked_at",
            "revoked_by_email",
            "last_seen_at",
            "expires_at",
            "created_at",
            "is_current",
        )
        read_only_fields = fields

    def get_is_current(self, obj: AuthSession) -> bool:
        """آیا این نشست، همان نشستِ درخواستِ فعلی است؟ (از claimِ sid توکن)"""
        request = self.context.get("request")
        token = getattr(request, "auth", None)
        sid = token.get(SESSION_ID_CLAIM) if token is not None else None
        return sid is not None and str(sid) == str(obj.pk)


class SessionAwareTokenRefreshSerializer(TokenRefreshSerializer):
    """
    رفرشِ JWT با اعمالِ پیوندِ نشست (sid).

    پیش از هر چرخه‌ای، نشستِ متناظر با claimِ sid چک می‌شود: نشستِ لغوشده
    یا پاک‌شده → InvalidToken (۴۰۱) — در نتیجه دستگاهِ لغوشده نه با access
    زنده می‌ماند (اخراجِ فوری توسط SessionAwareJWTAuthentication) و نه با
    refresh جدید. نشستِ سالم: عبور + لمسِ last_seen_at (رفرش هم «فعالیت» است)
    و همان claimِ sid یک‌به‌یک در توکنِ چرخیده حفظ می‌شود.

    چرا rotation این‌جا خودمان انجام می‌شود (به‌جای super().validate):
        TokenRefreshSerializer برای خواندنِ ROTATE_REFRESH_TOKENS به یک
        api_settingsِ import-time تکیه دارد که در تست‌رانرهای بزرگ — با
        تعویضِ settings توسط فیکسچرها — ممکن است به نمونه‌ی کهنه بچسبد.
        خواندنِ تازه‌ی api_settings در همین متد، رفتار را در هر محیط
        قطعی می‌کند؛ منطق دقیقاً همان الگوی SimpleJWT است.
    """

    def validate(self, attrs: dict) -> dict:
        from rest_framework_simplejwt.settings import api_settings

        try:
            refresh = RefreshToken(attrs["refresh"])
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc

        # اعتبارسنجیِ کاربر — همان قاعده‌ی استانداردِ SimpleJWT
        user_id = refresh.payload.get(api_settings.USER_ID_CLAIM, None)
        if user_id is not None:
            user = User.objects.filter(pk=user_id).first()
            if user is None or not api_settings.USER_AUTHENTICATION_RULE(user):
                raise InvalidToken("کاربر فعال برای این توکن یافت نشد.")

        # قفلِ نشست: رفرشِ نشستِ لغوشده/ناموجود ممنوع (راهِ فرارِ rotation بسته)
        sid = refresh.get(SESSION_ID_CLAIM)
        session = None
        if sid is not None:
            session = AuthSession.objects.only("is_revoked").filter(pk=sid, user_id=user_id).first()
            if session is None or session.is_revoked:
                raise InvalidToken(SESSION_REVOKED_MESSAGE)

        data = {"access": str(refresh.access_token)}

        if api_settings.ROTATE_REFRESH_TOKENS:
            if api_settings.BLACKLIST_AFTER_ROTATION:
                # موجودیتِ blacklist دفاعی چک می‌شود (اگر app نصب نباشد)
                blacklist = getattr(refresh, "blacklist", None)
                if callable(blacklist):
                    blacklist()
            refresh.set_jti()
            refresh.set_exp()
            refresh.set_iat()
            outstand = getattr(refresh, "outstand", None)
            if callable(outstand):
                outstand()
            data["refresh"] = str(refresh)

        if session is not None:
            AuthSession.objects.filter(pk=session.pk, is_revoked=False).update(
                last_seen_at=timezone.now()
            )
        return data


class AuthRiskSignalSerializer(serializers.ModelSerializer):
    """Read serializer for authentication risk signals."""

    user_email = serializers.EmailField(source="user.email", read_only=True, allow_null=True)
    reviewed_by_email = serializers.EmailField(
        source="reviewed_by.email", read_only=True, allow_null=True
    )
    signal_type_display = serializers.CharField(source="get_signal_type_display", read_only=True)
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = AuthRiskSignal
        fields = (
            "id",
            "signal_type",
            "signal_type_display",
            "severity",
            "severity_display",
            "status",
            "status_display",
            "user",
            "user_email",
            "session",
            "ip_address",
            "description",
            "metadata",
            "reviewed_by_email",
            "reviewed_at",
            "review_note",
            "created_at",
        )
        read_only_fields = fields


class AuthRiskSignalReviewSerializer(serializers.Serializer):
    """Input serializer for reviewing authentication risk signals."""

    status = serializers.ChoiceField(
        choices=(
            (AuthRiskStatus.REVIEWED, AuthRiskStatus.REVIEWED.label),
            (AuthRiskStatus.DISMISSED, AuthRiskStatus.DISMISSED.label),
            (AuthRiskStatus.ESCALATED, AuthRiskStatus.ESCALATED.label),
        ),
    )
    review_note = serializers.CharField(required=False, allow_blank=True, default="")
