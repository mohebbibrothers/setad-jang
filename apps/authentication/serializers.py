from __future__ import annotations

from typing import Final

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .choices import Gender, UserRole
from .models import PrimaryIdentifierKind, Profile, User
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
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_email(self, value: str) -> str:
        try:
            return normalize_email(value)
        except DjangoValidationError as exc:
            raise _build_drf_validation_error(exc) from exc


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(min_length=OTP_CODE_LENGTH, max_length=OTP_CODE_LENGTH)

    def validate_email(self, value: str) -> str:
        try:
            return normalize_email(value)
        except DjangoValidationError as exc:
            raise _build_drf_validation_error(exc) from exc


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        try:
            return normalize_email(value)
        except DjangoValidationError as exc:
            raise _build_drf_validation_error(exc) from exc


class RefreshTokenInputSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        try:
            return normalize_email(value)
        except DjangoValidationError as exc:
            raise _build_drf_validation_error(exc) from exc


class ResetPasswordSerializer(serializers.Serializer):
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
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=100)


class UpdateProfileSerializer(serializers.Serializer):
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
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    is_active = serializers.BooleanField(required=False)
    is_email_verified = serializers.BooleanField(required=False)


class AdminChangeRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=UserRole.choices)
