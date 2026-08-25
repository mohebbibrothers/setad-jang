"""
ثابت‌های پیوند «توکن JWT ↔ نشستِ احراز (AuthSession)».

چرا این ماژول وجود دارد:
    سه مصرف‌کننده (services / jwt_auth / serializers) به یک نامِ claim و
    یک پیامِ خطای واحد نیاز دارند؛ نگه‌داشتن آن‌ها در یک نقطه‌ی خنثی و
    بدون وابستگی (نه DRF، نه SimpleJWT، نه مدل) هیچ چرخه‌ی importای
    نمی‌سازد و هر لایه می‌تواند آزادانه import کند.

قرارداد:
    SESSION_ID_CLAIM دومین کلیدِ اعتماد است — هر access/refreshِ تازه
    پس از لاگین، شناسه‌ی AuthSession خود را در این claim حمل می‌کند و
    با rotation هم (به‌لطف نگه‌داشتِ claim در SimpleJWT) حفظ می‌شود.
"""

from __future__ import annotations

from typing import Final

#: نامِ claimای که pk نشست را داخل JWT حمل می‌کند.
SESSION_ID_CLAIM: Final = "sid"

#: پیامِ یکدست برای هر دو مسیرِ رد: درخواستِ API (۴۰۱ احراز) و رفرش (InvalidToken).
SESSION_REVOKED_MESSAGE: Final = "نشست کاربری شما لغو یا منقضی شده است. لطفاً دوباره وارد شوید."

#: آستانه‌ی لمسِ last_seen_at — حداکثر یک UPDATE در هر این‌قدر ثانیه برای هر نشست.
LAST_SEEN_TOUCH_SECONDS: Final = 60
