"""
WSGI config for Setad Jang project.

این فایل WSGI callable را به‌عنوان `application` در سطح ماژول expose می‌کند.
از این فایل برای deployment با WSGI server (مثل Gunicorn, uWSGI, cPanel Passenger)
استفاده می‌شود.

For more information on this file, see:
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os
import re
from urllib.parse import unquote_to_bytes

from django.core.wsgi import get_wsgi_application

# ─── تنظیمات پیش‌فرض ───────────────────────────────────
# در production، DJANGO_SETTINGS_MODULE باید قبلاً به
# `config.settings.production` ست شده باشد (در systemd unit،
# Dockerfile، passenger_wsgi.py، یا environment variables سرور).
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings.development",
)

_django_application = get_wsgi_application()

# ─── فیکسِ PEP 3333 برای «PATH_INFO انکودمانده» (Passengerِ cPanel) ──
# Passenger روی هاست اشتراکیِ cPanel برخلاف قراردادِ استاندارد WSGI
# مسیر را بدون percent-decode تحویل می‌دهد:
#     /api/v1/lms/courses/%da%86.../   (اسلاگِ فارسی، خام)
# نتیجه بدون این چارچوب: هیچ اسلاگ غیرASCIIای با دیتابیس match نمی‌شود —
# «کلاس پیدا نشد» برای تمام دوره‌های اسلاگ‌فارسی، و ۴۰۴ برای رسانه‌های
# نام‌فارسی. قراردادِ درستِ PEP 3333 این است که سرور «بایت‌های دیکدشده»
# را به‌صورت رشته‌ی latin-1 تحویل دهد تا جنگو با get_bytes_from_wsgi
# همان بایت‌ها را دوباره به UTF-8 برگرداند.
#
# شرط‌های واردعمل‌شدن (هر دو لازم):
#   ۱) مسیر دست‌کم یک توکنِ %{hex}{hex} داشته باشد، و
#   ۲) کلِ مسیر پس از unquote به UTF-8ِ معتبر دیکد شود.
# روی سرورهای درست‌رفتار (gunicorn، dev server) مسیر یا فاقد «%» است یا
# unquote به UTF-8ِ نامعتبر می‌انجامد → بدون تغییر عبور می‌کند؛ یعنی
# میان‌باف idempotent است. environ هرگز in-place دست‌کاری نمی‌شود.

_ENCODED_CHUNK_RE = re.compile(r"%[0-9A-Fa-f]{2}")


def fix_wsgi_path_info(environ: dict) -> dict:
    """PATH_INFO هنوز-انکود را به فرمِ PEP 3333 (بایت‌هایِ latin-1) برمی‌گرداند."""
    path_info = environ.get("PATH_INFO")
    if (
        not isinstance(path_info, str)
        or "%" not in path_info
        or not _ENCODED_CHUNK_RE.search(path_info)
    ):
        return environ

    raw = unquote_to_bytes(path_info)
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return environ

    environ = dict(environ)
    environ["PATH_INFO"] = raw.decode("latin-1")
    return environ


def application(environ, start_response):
    """نقطه‌ی ورود WSGI با لایه‌ی اصلاحِ PATH_INFO پیش از جنگو."""
    return _django_application(fix_wsgi_path_info(environ), start_response)
