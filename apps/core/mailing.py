"""
ارسال ایمیل از طریق mailer یکتای Django (``settings.MAILERS``).

چرا این ماژول
------------
از Django 6.1 توابع قدیمی ``django.core.mail.send_mail`` و
``get_connection`` منسوخ شده‌اند (RemovedInDjango70Warning) و مسیر رسمی،
استفادهٔ مستقیم از ``MAILERS`` است:

    from django.core.mail import mailers
    mailer = mailers[alias]
    mailer.send_messages([message])

این ماژول همان قرارداد سادهٔ قبلی (subject/message/from_email/recipient_list)
را با پشت‌صحنهٔ جدید حفظ می‌کند تا call siteها تغییری در معنای خود ندهند.

قراردادهای رفتاری:
- همیشه fail loud است (معادل ``fail_silently=False`` قبلی)؛ شکست ارسال
  exception پرتاب می‌کند و caller تصمیم می‌گیرد.
- از ``MAILERS["default"]`` استفاده می‌کند؛ برای aliasهای دیگر فقط کافی است
  تابعی شبیه این با alias دلخواه ساخته شود.
"""

from __future__ import annotations

from collections.abc import Sequence

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, mailers

DEFAULT_MAILER_ALIAS: str = "default"


def send_text_email(
    *,
    subject: str,
    message: str,
    recipient_list: Sequence[str],
    from_email: str | None = None,
) -> int:
    """
    Send a plain-text email through the default mailer.

    Args:
        subject: عنوان ایمیل.
        message: متن سادهٔ ایمیل.
        recipient_list: گیرنده‌ها.
        from_email: فرستنده؛ پیش‌فرض ``settings.DEFAULT_FROM_EMAIL``.

    Returns:
        تعداد پیام‌های ارسال‌شده (معمولاً ۱).

    Raises:
        هر خطای backend (مثلاً SMTPException) — همیشه fail loud.
    """
    from_email = from_email or settings.DEFAULT_FROM_EMAIL
    email = EmailMultiAlternatives(
        subject=subject,
        body=message,
        from_email=from_email,
        to=list(recipient_list),
    )
    mailer = mailers[DEFAULT_MAILER_ALIAS]
    return mailer.send_messages([email])
