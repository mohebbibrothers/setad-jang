"""
Project-wide pytest configuration.

این فایل root-level fixtures پروژه را تعریف می‌کند تا:
- تست‌ها در همه‌ی appها از یک API client استاندارد استفاده کنند
- ساخت کاربر/ادمین به‌صورت هماهنگ و قابل اتکا انجام شود
- throttling و cache برای جلوگیری از flaky test، در سطح session
  به حالت deterministic درآیند
- Celery در حالت eager اجرا شود تا taskها بدون نیاز به worker/broker
  در همان process تست تمام شوند
- ALLOWED_HOSTS شامل 'testserver' باشد تا تست‌های APIClient (مخصوصاً
  multipart uploadها) بدون DisallowedHost کار کنند.

اصول طراحی:
- import های وابسته به Django settings در سطح ماژول انجام نمی‌شوند،
  چون pytest-django هنوز Django را bootstrap نکرده است.
- به‌جای آن، importها داخل fixtureها انجام می‌شوند تا lazy loading
  حفظ شود و bootstrap order درست بماند.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

# ============================================================
# Session-level: throttling & cache hygiene
# ============================================================


@pytest.fixture(autouse=True)
def _disable_throttling(settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    در همه‌ی تست‌ها throttling را غیرفعال می‌کند.

    دلیل:
    throttle یک side-effect حاکم بر زمان است و می‌تواند تست‌ها را flaky کند.
    در محیط تست همیشه باید deterministic باشیم.

    نکته مهم:
    تغییر صرفِ REST_FRAMEWORK settings برای viewهایی که throttle_classes
    اختصاصی دارند کافی نیست، چون DRF در زمان request ممکن است همان
    throttleها را instantiate کند و روی scope lookup خطا بدهد.

    بنابراین علاوه بر صفر کردن settings، خود check_throttles را هم
    به‌صورت test-only no-op می‌کنیم.
    """
    from rest_framework.views import APIView

    rest_framework_settings = settings.REST_FRAMEWORK.copy()
    rest_framework_settings["DEFAULT_THROTTLE_CLASSES"] = ()
    rest_framework_settings["DEFAULT_THROTTLE_RATES"] = {}
    settings.REST_FRAMEWORK = rest_framework_settings

    monkeypatch.setattr(APIView, "check_throttles", lambda self, request: None)


@pytest.fixture(autouse=True)
def _clear_cache_between_tests() -> Iterator[None]:
    """
    قبل و بعد هر تست cache را پاک می‌کند.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


# ============================================================
# Security hygiene for tests
# ============================================================


@pytest.fixture(autouse=True)
def _secure_test_secret_key(settings) -> None:
    """
    تنظیم یک SECRET_KEY امن و بلند فقط برای محیط تست.

    دلیل:
    برخی تست‌ها JWT واقعی generate می‌کنند و PyJWT برای کلیدهای HMAC
    کوتاه‌تر از 32 بایت warning می‌دهد. ما می‌خواهیم pipeline تست
    zero-warning باشد، بدون اینکه development/production واقعی را دست بزنیم.

    نکته مهم:
    فقط تغییر SECRET_KEY کافی نیست، چون SimpleJWT از settings cached خودش
    استفاده می‌کند. بنابراین SIGNING_KEY را هم override می‌کنیم و
    api_settings را reload می‌کنیم.
    """
    from rest_framework_simplejwt.settings import api_settings as simplejwt_api_settings

    secure_key = "test-secret-key-with-at-least-32-bytes-2026"

    settings.SECRET_KEY = secure_key

    simple_jwt_settings = settings.SIMPLE_JWT.copy()
    simple_jwt_settings["SIGNING_KEY"] = secure_key
    settings.SIMPLE_JWT = simple_jwt_settings

    simplejwt_api_settings.reload()


@pytest.fixture(autouse=True)
def _allow_test_host(settings) -> None:
    """
    اطمینان از وجود 'testserver' در ALLOWED_HOSTS برای محیط تست.

    دلیل:
    APIClient درخواست‌ها را با HTTP_HOST='testserver' ارسال می‌کند.
    اگر این host در ALLOWED_HOSTS نباشد، Django CommonMiddleware در
    request.get_host() خطای DisallowedHost پرتاب می‌کند و response را
    به 400 تبدیل می‌نماید. این مشکل خصوصاً در تست‌های multipart upload
    که Django نیاز به ساخت absolute URL برای فایل‌ها دارد ظاهر می‌شود.

    این fixture فقط در محیط تست عمل می‌کند و development/production را
    تحت تأثیر قرار نمی‌دهد.
    """
    current_hosts = list(settings.ALLOWED_HOSTS) if settings.ALLOWED_HOSTS else []
    if "testserver" not in current_hosts:
        current_hosts.append("testserver")
        settings.ALLOWED_HOSTS = current_hosts


# ============================================================
# Celery — eager execution for tests
# ============================================================


@pytest.fixture(autouse=True)
def _celery_eager_mode(settings) -> None:
    """
    اجرای Celery در حالت eager برای تمام تست‌ها.
    """
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    settings.CELERY_BROKER_URL = "memory://"
    settings.CELERY_RESULT_BACKEND = "cache+memory://"


# ============================================================
# API client fixtures
# ============================================================


@pytest.fixture
def api_client():
    """
    یک DRF APIClient ساده و بدون احراز هویت.
    """
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def authenticated_client(api_client, regular_user):
    """
    APIClient احراز هویت شده با یک کاربر عادی.
    """
    api_client.force_authenticate(user=regular_user)
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user):
    """
    APIClient احراز هویت شده با یک کاربر ادمین.
    """
    api_client.force_authenticate(user=admin_user)
    return api_client


# ============================================================
# User fixtures
# ============================================================


@pytest.fixture
def regular_user(db):
    """
    یک کاربر عادی فعال برای استفاده در تست‌های احراز هویت/پروفایل.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(
        email="user@test.local",
        password="StrongPass!234",
    )


@pytest.fixture
def admin_user(db):
    """
    یک کاربر ادمین فعال برای endpointهای مدیریتی.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.create_user(
        email="admin@test.local",
        password="StrongPass!234",
    )

    if hasattr(user, "role"):
        user.role = "admin"
    user.is_staff = True
    user.is_superuser = True
    user.save()

    return user
