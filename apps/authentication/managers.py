"""
Custom querysets and managers for the authentication user model.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import BaseUserManager

from apps.core.managers import BaseQuerySet

from .choices import UserRole

_IDENTIFIER_EMAIL = "email"
_IDENTIFIER_PHONE = "phone"


class UserQuerySet(BaseQuerySet):
    """UserQuerySet implementation for the authentication application."""

    def admins(self):
        return self.filter(role=UserRole.ADMIN)

    def regular_users(self):
        return self.filter(role=UserRole.USER)

    def verified(self):
        return self.filter(is_email_verified=True)


class UserManager(BaseUserManager):
    """
    Manager سفارشی کاربر.

    اهداف:
    - فقط یوزرهای active را در queryset پیش‌فرض برگرداند
    - create_user را multi-identifier-aware کند
    - backward compatibility با flow قدیمی email-first حفظ شود
    - create_superuser همچنان email-first و سخت‌گیر باقی بماند
    """

    use_in_migrations = True

    def get_queryset(self):
        return UserQuerySet(self.model, using=self._db).filter(is_active=True)

    def _normalize_optional_email(self, email: str | None) -> str | None:
        if email is None:
            return None

        email = email.strip()
        if not email:
            return None

        return self.normalize_email(email)

    def _normalize_optional_phone(self, phone_number: str | None) -> str | None:
        if phone_number is None:
            return None

        phone_number = phone_number.strip()
        if not phone_number:
            return None

        return phone_number

    def _resolve_primary_identifier(
        self,
        *,
        email: str | None,
        phone_number: str | None,
        extra_fields: dict[str, Any],
    ) -> str:
        """
        تعیین primary_identifier به‌صورت مرکزی.

        Rules:
        - اگر caller explicitly داده باشد، validate می‌کنیم
        - اگر نداده باشد:
          - در صورت وجود email → email
          - در غیر این صورت → phone
        """
        primary_identifier = extra_fields.get("primary_identifier")

        if primary_identifier is None:
            return _IDENTIFIER_EMAIL if email else _IDENTIFIER_PHONE

        if primary_identifier == _IDENTIFIER_EMAIL and not email:
            raise ValueError("وقتی شناسه اصلی ایمیل است، email الزامی است.")

        if primary_identifier == _IDENTIFIER_PHONE and not phone_number:
            raise ValueError("وقتی شناسه اصلی شماره موبایل است، phone_number الزامی است.")

        return primary_identifier

    def _create_user(
        self,
        email: str | None,
        password: str | None,
        **extra_fields: Any,
    ):
        phone_number = self._normalize_optional_phone(
            extra_fields.pop("phone_number", None),
        )
        email = self._normalize_optional_email(email)

        if email is None and phone_number is None:
            raise ValueError("ایمیل یا شماره موبایل الزامی است.")

        extra_fields["primary_identifier"] = self._resolve_primary_identifier(
            email=email,
            phone_number=phone_number,
            extra_fields=extra_fields,
        )

        user = self.model(
            email=email,
            phone_number=phone_number,
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(
        self,
        email: str | None = None,
        password: str | None = None,
        **extra_fields: Any,
    ):
        extra_fields.setdefault("role", UserRole.USER)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)

        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self,
        email: str | None,
        password: str | None = None,
        **extra_fields: Any,
    ):
        if not email:
            raise ValueError("سوپریوزر باید ایمیل داشته باشد.")

        extra_fields.setdefault("role", UserRole.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_email_verified", True)
        extra_fields.setdefault("primary_identifier", _IDENTIFIER_EMAIL)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("سوپریوزر باید is_staff=True باشد.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("سوپریوزر باید is_superuser=True باشد.")

        return self._create_user(email, password, **extra_fields)


class UserAllManager(BaseUserManager):
    """Manager که همه یوزرها (شامل غیرفعال‌ها) را برمی‌گرداند."""

    def get_queryset(self):
        return UserQuerySet(self.model, using=self._db)
