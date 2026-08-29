"""تست‌های گارد لاگین ادمین (یافتهٔ P1-۳ فاز ۷).

قراردادهایی که قفل می‌شوند:
- آستانه بر اساس «شکست» است، نه تعداد درخواست؛ پنج ورودِ نامعتبر → قفل.
- قفل روی POST /admin/login/ اثر می‌گذارد (429 + Retry-After) و بقیهٔ
  مسیرهای /admin/ و کل API دست‌نخورده‌اند.
- ورودِ موفق شمارنده‌ها را صفر می‌کند.
- شمارشِ API login هرگز قفل ادمین را درگیر نمی‌کند (و بالعکس).
- کلیدها نرمال‌اند: بزرگی/کوچکی و فاصلهٔ نام‌کاربری یکی شمرده می‌شود.

نکتهٔ تست‌نویسی: throttle و cache بین تست‌ها توسط conftest پاک می‌شود؛ این
فایل عمداً به جای fixture پیش‌فرض از `settings` override استفاده می‌کند تا
آستانه‌ها صریح و مستقل از پیش‌فرض‌های global باشند.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

_ADMIN_LOGIN = "/admin/login/"
_ADMIN_HOME = "/admin/"
_BAD_PASSWORD = "Wr0ng!Password-42"


def _attempt(client, *, username: str, password: str):
    return client.post(_ADMIN_LOGIN, data={"username": username, "password": password})


def test_lockout_after_threshold_blocks_next_attempt(admin_user, client, settings) -> None:
    """پنج شکست → ششم 429 با Retry-After، حتی اگر رمز درست باشد."""
    settings.ADMIN_LOGIN_MAX_FAILURES = 5
    settings.ADMIN_LOGIN_MAX_FAILURES_PER_IP = 100
    settings.ADMIN_LOGIN_LOCKOUT_SECONDS = 900

    for attempt in range(1, 6):
        response = _attempt(client, username=admin_user.email, password=_BAD_PASSWORD)
        assert response.status_code == 200, f"attempt {attempt} باید هنوز مجاز باشد"

    # ششمین تلاش — با رمز درست — باید عملاً قفل باشد؛ ثابت می‌کند تصمیم
    # پیش از view گرفته می‌شود و findingِ رمز، قفل را دور نمی‌زند.
    blocked = _attempt(client, username=admin_user.email, password="StrongPass!234")
    assert blocked.status_code == 429
    assert int(blocked["Retry-After"]) > 0


def test_other_admin_pages_not_blocked_by_login_lockout(admin_user, client, settings) -> None:
    """قفلِ لاگین، دسترسیِ صفحات ادمین برای کاربرِ لاگین‌شده را نمی‌بندد."""
    settings.ADMIN_LOGIN_MAX_FAILURES = 2
    settings.ADMIN_LOGIN_MAX_FAILURES_PER_IP = 100

    # حلقه روی یک هویت (admin email) قفل را فعال می‌کند؛ ادعای اصلی تست:
    # قفلِ لاگین، صفحهٔ خودِ پنل را برای ادمینِ لاگین‌شده نمی‌بندد.
    for _ in range(3):
        _attempt(client, username=admin_user.email, password=_BAD_PASSWORD)

    # همان هویتِ قفل‌شده واقعاً 429 می‌گیرد…
    assert _attempt(client, username=admin_user.email, password="y").status_code == 429
    # …و یک نام‌کاربریِ دیگر (زوجِ تازه، زیر آستانهٔ IP) قفلِ زوج را به ارث
    # نمی‌برد — اثباتِ per-(IP,username) بودنِ کلید، نه سراسری بودنش.
    assert _attempt(client, username="brand-new@test.local", password="y").status_code == 200

    client.force_login(admin_user)
    assert client.get(_ADMIN_HOME).status_code == 200


def test_successful_login_resets_failure_counters(admin_user, client, settings) -> None:
    """ورودِ موفق باید شمارنده را صفر کند تا اشتباهاتِ تصادفی قفل نسازند."""
    settings.ADMIN_LOGIN_MAX_FAILURES = 5
    settings.ADMIN_LOGIN_MAX_FAILURES_PER_IP = 100

    for _ in range(4):
        assert (
            _attempt(client, username=admin_user.email, password=_BAD_PASSWORD).status_code == 200
        )

    ok = _attempt(client, username=admin_user.email, password="StrongPass!234")
    assert ok.status_code == 302
    client.logout()

    # بعد از موفقیت شمارنده صفر است: چهار شکستِ تازه آزاد، پنجمی قفل را
    # «می‌سازد» (خودش هنوز 200 است چون تصمیمِ قفل، پیش از view گرفته می‌شود)
    # و ششم 429 می‌گیرد — دقیقاً همان قراردادِ test_lockout بالا.
    for attempt in range(1, 5):
        assert (
            _attempt(client, username=admin_user.email, password=_BAD_PASSWORD).status_code == 200
        ), f"attempt {attempt} نباید قفل می‌بود"
    assert _attempt(client, username=admin_user.email, password=_BAD_PASSWORD).status_code == 200
    assert _attempt(client, username=admin_user.email, password=_BAD_PASSWORD).status_code == 429


def test_per_ip_threshold_catches_distributed_username_spray(admin_user, client, settings) -> None:
    """نام‌های کاربری متنوع از یک IP باید با آستانهٔ تجمیعی گرفته شود."""
    settings.ADMIN_LOGIN_MAX_FAILURES = 100  # آستانهٔ زوج عملاً خاموش
    settings.ADMIN_LOGIN_MAX_FAILURES_PER_IP = 3

    for i in range(3):
        assert (
            _attempt(client, username=f"victim{i}@test.local", password=_BAD_PASSWORD).status_code
            == 200
        )

    assert (
        _attempt(client, username="victim9@test.local", password=_BAD_PASSWORD).status_code == 429
    )


def test_api_login_failures_do_not_lock_admin_login(client, admin_user, settings) -> None:
    """مصرف‌کننده‌های API نباید گارد ادمین را آلوده کنند (سیگنال مشترک است)."""
    settings.ADMIN_LOGIN_MAX_FAILURES = 2
    settings.ADMIN_LOGIN_LOCKOUT_SECONDS = 900

    for _ in range(10):
        response = client.post(
            "/api/v1/auth/login/password/",
            data={"identifier": "whoever@test.local", "password": _BAD_PASSWORD},
            content_type="application/json",
        )
        assert response.status_code == 401

    # با وجود ده شکستِ API، لاگین ادمین باید کار کند.
    assert _attempt(client, username=admin_user.email, password="StrongPass!234").status_code == 302


def test_username_key_is_normalized(admin_user, client, settings) -> None:
    """بزرگی/کوچکی و فاصلهٔ اضافه در نام‌کاربری نباید شمارنده را جابه‌جا کند."""
    settings.ADMIN_LOGIN_MAX_FAILURES = 3
    settings.ADMIN_LOGIN_MAX_FAILURES_PER_IP = 100

    variants = [
        f" {admin_user.email.upper()} ",
        admin_user.email,
        admin_user.email.title(),
    ]
    for username in variants:
        assert _attempt(client, username=username, password=_BAD_PASSWORD).status_code == 200

    assert _attempt(client, username=admin_user.email, password=_BAD_PASSWORD).status_code == 429


def test_get_login_page_is_not_counted(admin_user, client, settings) -> None:
    """صفحهٔ فرم (GET) هرگز نباید شکست بشمارد."""
    settings.ADMIN_LOGIN_MAX_FAILURES = 2
    settings.ADMIN_LOGIN_MAX_FAILURES_PER_IP = 100

    for _ in range(5):
        assert client.get(_ADMIN_LOGIN).status_code == 200
