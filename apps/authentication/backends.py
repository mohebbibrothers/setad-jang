"""
Custom Authentication Backends.

این ماژول backendهای سفارشی برای احراز هویت را در بر می‌گیرد.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Q
from django.http import HttpRequest

User = get_user_model()


class MultiIdentifierBackend(ModelBackend):
    """
    Backend احراز هویت با پشتیبانی از چند شناسه (ایمیل یا شماره موبایل).

    دلیل پیاده‌سازی:
    ModelBackend پیش‌فرض جنگو فقط از USERNAME_FIELD (که اینجا email است)
    پشتیبانی می‌کند. این کلاس اجازه می‌دهد کاربر با شماره موبایل هم لاگین کند
    (مثلاً در پنل ادمین جنگو یا از طریق کتابخانه‌های احراز هویت).
    """

    def authenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> AbstractBaseUser | None:
        """
        احراز هویت کاربر.

        آرگومان `username` برای سازگاری با signature پیش‌فرض جنگو و کتابخانه‌ها
        نگه داشته شده است. در صورت خالی بودن، مقدار از `kwargs` با کلیدهای
        `email` یا `identifier` استخراج می‌شود.
        """
        identifier = username or kwargs.get("email") or kwargs.get("identifier")

        if not identifier:
            return None

        try:
            # جستجو با ایمیل (غیر حساس به حروف کوچک/بزرگ) یا شماره موبایل دقیق
            user = User.objects.get(Q(email__iexact=identifier) | Q(phone_number=identifier))
        except User.DoesNotExist:
            # Mitigation برای Timing Attack:
            # اجرای یک round هشینگ رمز عبور حتی اگر کاربر وجود نداشته باشد،
            # تا زمان پاسخ‌دهی برای کاربران موجود و ناموجود یکسان باشد.
            User().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None
