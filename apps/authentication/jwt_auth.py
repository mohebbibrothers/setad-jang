"""
SessionAwareJWTAuthentication — احرازِ هویتِ JWT وابسته به نشست.

چرا این کلاس وجود دارد (ریشه‌ی دو باگِ گزارش‌شده):
    ۱) «آخرین فعالیت» همیشه تاریخِ ورود را نشان می‌داد چون last_seen_at
       فقط لحظه‌ی لاگین نوشته می‌شد؛ حالا هر درخواستِ احرازشده (با آستانه‌ی
       ۶۰ ثانیه) آن را لمس می‌کند.
    ۲) «لغو نشست» هیچ اثری نداشت چون هیچ‌جا access token با is_revoked
       چک نمی‌شد و rotation نیز jti ذخیره‌شده را پشت سر می‌گذاشت؛ حالا
       claimِ sid توکن را به AuthSession می‌دوزد و نشستِ لغوشده در اولین
       درخواستِ بعدی 401 می‌شود.

نقطه‌ی اتصال: config/settings/base.py → DEFAULT_AUTHENTICATION_CLASSES.
منطقِ سنگین در services.validate_and_touch_session است تا این فایل فقط
آداپتورِ نازکِ DRF باشد.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from .constants import SESSION_REVOKED_MESSAGE
from .services import validate_and_touch_session


class SessionAwareJWTAuthentication(JWTAuthentication):
    """JWTAuthentication + اعمالِ وضعیت نشست (لغو → 401) و لمسِ آخرین فعالیت."""

    def authenticate(self, request: Any) -> Any:
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        if not validate_and_touch_session(user=user, token_claims=token):
            raise AuthenticationFailed(SESSION_REVOKED_MESSAGE)
        return result


class SessionAwareJWTAuthenticationScheme(SimpleJWTScheme):
    """معرفیِ کلاسِ احرازِ سفارشی به drf-spectacular — همان security scheme‌ای
    با همان نامِ قبلی (jwtAuth) تا اسناد OpenAPI هیچ تغییری نکنند."""

    target_class = "apps.authentication.jwt_auth.SessionAwareJWTAuthentication"
    name = "jwtAuth"
