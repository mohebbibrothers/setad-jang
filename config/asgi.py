"""
ASGI config for Setad Jang project.

این فایل ASGI callable را به‌عنوان `application` در سطح ماژول expose می‌کند.
از این فایل برای deployment با ASGI server (مثل Uvicorn, Daphne, Hypercorn)
استفاده می‌شود.

For more information on this file, see:
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

# ─── تنظیمات پیش‌فرض ───────────────────────────────────
# در production، DJANGO_SETTINGS_MODULE باید قبلاً به
# `config.settings.production` ست شده باشد (در systemd unit،
# Dockerfile، یا environment variables سرور).
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings.development",
)

application = get_asgi_application()
