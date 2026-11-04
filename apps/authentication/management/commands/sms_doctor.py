"""SMS Doctor — عیب‌یابیِ کاملِ «چرا پیامک نمی‌رسد؟» با یک دستور.

سه لایه، به ترتیبِ شایع‌ترین عللِ خرابی در پروداکشن:

1. **قراردادِ تنظیمات**: ``OTP_SMS_PROVIDER`` (iranpayamak یا console؟!)،
   ``OTP_PROVIDER`` و ``NOTIFICATIONS_SMS_ENABLED``. مقدارِ پیش‌فرضِ
   console یعنی هیچ پیامکی واقعاً ارسال نمی‌شود — OTP در production خطای
   صریح می‌دهد و پیامکِ نوتیفیکیشن بی‌صدا ``FAILED`` علامت می‌خورد. این
   بیشترین علتِ «همهٔ پیامک‌ها مرده‌اند، بااین‌که الگوها در پنل فعال‌اند».
2. **اکمالِ پیکربندیِ درگاه**: کلیدِ API و کدِ الگوی هر purpose — از
   ``check_sms_provider_readiness`` (همان چیزی که در healthz هم دیده
   می‌شود) — تا الگویِ نوتیفیکیشن هم وقتی کانالش روشن است الزامی شمرد.
3. **آزمونِ زنده با ``--to``**: یک پیامکِ واقعی با همان تنظیماتِ جاری
   ارسال می‌شود و پاسخِ خامِ درگاه (HTTP + متنِ ایران‌پیامک) چاپ می‌شود؛
   تفکیکِ «از سمتِ ما نمی‌رسد» از «درگاه رد می‌کند» (الگوی تأییدنشده،
   عدمِ تطبیقِ خط، اعتبار، شبکه).

خروجی هیچ‌گاه کلیدِ API را چاپ نمی‌کند (فقط طول) — برای پیوست‌کردن به
تیکتِ پشتیبانی امن است. کدِ خروجی: ۰ = همه‌چیز سالم؛ ۱ = مشکل یافت شد
(قابل استفاده به‌عنوان گیتِ پیش‌دیپلوی).

استفاده در سرور:
    python manage.py sms_doctor
    python manage.py sms_doctor --to 09121234567 --purpose login
"""

from __future__ import annotations

import argparse
import io
import logging
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.authentication.logging_utils import mask_identifier
from apps.core.provider_readiness import check_sms_provider_readiness


class Command(BaseCommand):
    """گزارشِ آمادگیِ SMS + ارسالِ آزمایشی با پاسخِ خامِ درگاه."""

    help = (
        "بررسیِ تنظیمات و آمادگیِ فرستندهٔ پیامک؛ با --to یک ارسالِ واقعیِ "
        "آزمایشی انجام می‌دهد و پاسخِ درگاه را چاپ می‌کند."
    )

    _PURPOSES = ("login", "signup", "password_reset", "identifier_add", "notification")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--to",
            dest="to",
            default="",
            help="شمارهٔ مقصد برای ارسالِ پیامکِ آزمایشیِ واقعی (مثلاً 09121234567).",
        )
        parser.add_argument(
            "--purpose",
            default="login",
            choices=list(self._PURPOSES),
            help="الگوی مورد استفاده در ارسالِ آزمایشی (پیش‌فرض: login).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        problems: list[str] = []
        out = self.stdout

        provider = getattr(settings, "OTP_SMS_PROVIDER", "console")
        out.write(f"OTP_PROVIDER              = {getattr(settings, 'OTP_PROVIDER', '')}")
        out.write(f"OTP_SMS_PROVIDER          = {provider}")
        out.write(
            "NOTIFICATIONS_SMS_ENABLED = "
            f"{bool(getattr(settings, 'NOTIFICATIONS_SMS_ENABLED', False))}"
        )
        out.write(f"DEBUG                     = {bool(settings.DEBUG)}")

        if provider not in ("iranpayamak", "http"):
            problems.append(
                f"OTP_SMS_PROVIDER={provider!r} — هیچ پیامکِ واقعی ارسال نمی‌شود. "
                "در .env مقدار را روی iranpayamak بگذارید و سرویس را restart کنید."
            )

        readiness = check_sms_provider_readiness()
        out.write(
            f"readiness                 = ready={readiness.ready} mode={readiness.mode} · "
            f"{readiness.detail}"
        )
        if not readiness.ready:
            problems.append(f"readiness ناکام: {readiness.detail}")

        api_key = str(getattr(settings, "SMS_IRANPAYAMAK_API_KEY", "") or "")
        out.write(
            f"API key                   = {f'set ({len(api_key)} chars)' if api_key else 'NOT SET'}"
        )
        out.write(
            "line_number               = "
            f"{getattr(settings, 'SMS_IRANPAYAMAK_LINE_NUMBER', '')!r} · "
            f"number_format={getattr(settings, 'SMS_IRANPAYAMAK_NUMBER_FORMAT', '')!r}"
        )
        for purpose in self._PURPOSES:
            value = str(getattr(settings, f"SMS_IRANPAYAMAK_PATTERN_{purpose.upper()}", "") or "")
            out.write(f"pattern[{purpose:<15}] = {value or '— تنظیم‌نشده'}")

        to = str(options.get("to") or "").strip()
        if not to:
            self._finish(problems, hint="برای ارسالِ آزمایشیِ واقعی: --to 09xxxxxxxxx")
            return

        if provider not in ("iranpayamak", "http"):
            problems.append(
                "ارسالِ آزمایشی انجام نشد — ابتدا OTP_SMS_PROVIDER را در .env تنظیم کنید."
            )
            self._finish(problems)
            return

        self._live_send(to=to, purpose=str(options.get("purpose") or "login"))

    def _live_send(self, *, to: str, purpose: str) -> None:
        """ارسالِ واقعی از همان مسیرِ production؛ جزئیاتِ درگاه از log خوانده می‌شود."""
        from apps.authentication import providers as auth_providers

        logger = logging.getLogger("apps.authentication")
        buffer = io.StringIO()
        handler = logging.StreamHandler(buffer)
        logger.addHandler(handler)
        try:
            delivered = auth_providers.get_sms_otp_provider().send(
                recipient=to, code="123456", purpose=purpose
            )
        except Exception as exc:
            # جزئیاتِ درگاه فقط در لاگِ WARNING نوشته می‌شود (recipient در آنجا
            # mask شده)؛ اینجا عیناً به اپراتور نشان داده می‌شود تا مجبور نباشد
            # لاگ‌براور شود — تنها کانالِ خطا همین CommandError است.
            detail = buffer.getvalue().strip()
            suffix = f" — جزئیاتِ درگاه: {detail[-700:]}" if detail else ""
            raise CommandError(f"ارسالِ آزمایشی شکست خورد: {exc}{suffix}") from exc
        finally:
            logger.removeHandler(handler)

        if delivered:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✔ پیامکِ آزمایشی به {mask_identifier(to, identifier_kind='phone')} "
                    f"با الگوی {purpose!r} تحویلِ درگاه شد — اگر تا دو دقیقه نرسید، "
                    "صفحهٔ «پیام‌ها/صفانتظار» پنل ایران‌پیامک را ببینید."
                )
            )
            return
        raise CommandError("ارسالِ آزمایشی بدونِ خطا تمام شد ولی deliver نشد — غیرمنتظره است.")

    def _finish(self, problems: list[str], *, hint: str = "") -> None:
        if not problems:
            self.stdout.write(self.style.SUCCESS("✔ همهٔ لایه‌های SMS سالم‌اند."))
            return
        if hint:
            problems = [*problems, hint]
        raise CommandError("SMS Doctor — " + " ؛ ".join(problems))
