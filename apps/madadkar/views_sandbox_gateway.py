"""
صفحهٔ شبیه‌ساز درگاه پرداخت (sandbox gateway).

چرا این view وجود دارد؟
-----------------------
در گذشته ``SandboxProvider.request_payment`` به‌عنوان ``gateway_url``
خودِ آدرسِ callback را برمی‌گرداند (``…/payment/verify/?authority=…&sandbox=1``).
یعنی به‌محض «ادامه» در فرانت، مرورگر callback را می‌زد و پرداخت **بدون
هیچ تعاملی** SUCCESS می‌شد — رسید و همه‌چیز. علاوه بر تجربهٔ گمراه‌کننده،
هر رفرش/بوکمارک/اسکنری روی آن URL می‌توانست پرداختِ ساختگی تولید کند.

این view آن را به یک درگاه واقعیِ مینیاتوری تبدیل می‌کند:

- صفحه مبلغ و عنوان حرکت را از **خودِ رکورد Payment در DB** می‌خواند
  (هیچ مبلغی از query string پذیرفته نمی‌شود).
- دکمهٔ «تأیید پرداخت» → مکرِ تأیید روی رکورد نوشته می‌شود و مرورگر با
  ``Status=OK`` به callback می‌رود.
- دکمهٔ «انصراف» → ``Status=NOK`` (همان معنای لغو در درگاه‌های واقعی؛
  مسیر cancel بدون تماس با provider).
- بدون کلیک تأیید، ``SandboxProvider.verify_payment`` هرگز success
  نمی‌دهد — حتی اگر کسی مستقیم callback را صدا بزند.

امنیت/تهدیدها:
- دسترسی بدون احراز هویت است — دقیقاً مثل خودِ callback در حالت واقعی
  (کاربر در مرورگرِ بدون session هم از درگاه برمی‌گردد). «رمز» دسترسی،
  خودِ authority تصادفیِ ۳۲ بایتی است که قابل حدس نیست و صفحه فقط همان
  تراکنش را نشان می‌دهد/روی همان تراکنش marker می‌گذارد؛ هیچ پولی از
  کاربر گرفته نمی‌شود و در production اصلاً فعال نیست (گارد boot).
- CSRF: فرمِ همین صفحه POST می‌کند؛ attack مؤثر نیست چون بدون دانستن
  authority هیچ وضعیتی تغییر نمی‌کند و خودِ authority تنها کلیدِ کل
  flowِ callback است (که آن هم AllowAny است). برای سادگی csrf_exempt.
- فقط تراکنش‌های PENDING با gateway_name="sandbox" قابل عمل‌اند؛
  تراکنش موفق/ناموفق فقط اطلاع‌رسانی می‌شود (idempotent).
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.utils.html import escape
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from . import services
from .choices import PaymentStatus
from .models import Payment
from .views_common import _build_callback_url

logger = logging.getLogger("apps.madadkar")

_PAGE_CSS = """
body{font-family:Vazirmatn,Tahoma,sans-serif;background:#f4f6f8;margin:0;
     display:flex;min-height:100vh;align-items:center;justify-content:center;direction:rtl}
.card{background:#fff;border-radius:16px;box-shadow:0 8px 30px rgba(15,40,60,.10);
      max-width:430px;width:calc(100% - 32px);padding:28px 26px;text-align:center}
.badge{display:inline-block;background:#fff4d6;color:#8a5b00;border:1px solid #f0d494;
       border-radius:999px;padding:4px 14px;font-size:12px;margin-bottom:14px}
h1{font-size:17px;margin:0 0 6px;color:#17324a}
.amount{font-size:26px;font-weight:700;color:#0e6b46;margin:14px 0 2px}
.amount small{font-size:13px;color:#5b7186;font-weight:400}
.meta{color:#5b7186;font-size:12.5px;line-height:2;margin:10px 0 18px;word-break:break-all}
.buttons{display:flex;gap:10px}
button{flex:1;border:0;border-radius:10px;padding:12px 0;font-size:14.5px;cursor:pointer;
       font-family:inherit}
.ok{background:#0e6b46;color:#fff}.ok:hover{background:#0b583a}
.no{background:#eef1f4;color:#40566a}.no:hover{background:#e3e8ed}
.note{margin-top:16px;font-size:11.5px;color:#8296a8;line-height:1.9}
.status{padding:10px 12px;border-radius:10px;font-size:13.5px;margin:8px 0 2px}
.status.done{background:#e5f6ee;color:#0e6b46}
.status.dead{background:#fdecec;color:#a33030}
"""


def _render_page(
    *,
    title: str,
    amount: int | None,
    authority: str,
    campaign_title: str = "",
    body_html: str,
    show_form: bool,
    status_code: int = 200,
) -> HttpResponse:
    """ساخت پاسخ HTML خودبسندهٔ صفحهٔ شبیه‌ساز درگاه.

    خروجی یک سند HTML کامل و بدون وابستگی بیرونی است (CSS داخل line) —
    صفحه باید در مرورگرِ بدون build و بدون دسترسی به فرانت‌اند کار کند،
    چون دقیقاً مثل درگاه واقعی مقصدِ redirect است. هیچ متنی از داده‌های
    کاربر/DB بدون escape در HTML نمی‌نشیند.
    """
    amount_html = (
        f'<div class="amount">{amount:,}<small> تومان</small></div>' if amount is not None else ""
    )
    form_html = (
        """
        <form method="post" class="buttons">
          <button type="submit" name="action" value="confirm" class="ok">تأیید پرداخت</button>
          <button type="submit" name="action" value="cancel" class="no">انصراف</button>
        </form>
        """
        if show_form
        else ""
    )
    html = f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{_PAGE_CSS}</style>
</head>
<body>
  <div class="card">
    <span class="badge">درگاه آزمایشی (Sandbox) — هیچ پول واقعی جابه‌جا نمی‌شود</span>
    <h1>{escape(title)}</h1>
    {amount_html}
    <div class="meta">
      {escape(campaign_title) + "<br>" if campaign_title else ""}
      کد رهگیری: {escape(authority)}
    </div>
    {body_html}
    {form_html}
    <div class="note">
      این صفحه نقش درگاه واقعی را شبیه‌سازی می‌کند: تا «تأیید پرداخت» را
      نزنید، تراکنش در بک‌اند تأیید نمی‌شود؛ با «انصراف» هم سهم‌ها آزاد
      می‌شوند.
    </div>
  </div>
</body>
</html>"""
    return HttpResponse(html, status=status_code)


@method_decorator(csrf_exempt, name="dispatch")
class MadadkarPaymentSandboxGatewayView(APIView):
    """
    صفحهٔ تعاملیِ درگاه sandbox — GET/POST /api/v1/madadkar/payment/sandbox/<authority>/

    فقط در محیط‌های dev/test معنادار است (provider=sandbox)؛ در production
    settings اصلاً boot نمی‌شود اگر این provider انتخاب شده باشد.
    """

    authentication_classes: list = []
    permission_classes: list = []
    throttle_classes: list = []

    @extend_schema(exclude=True)
    def get(self, request: HttpRequest, authority: str) -> HttpResponse:
        payment = self._get_payment(authority)
        if payment is None:
            return self._render_not_found(authority)
        if payment.status == PaymentStatus.SUCCESS:
            return _render_page(
                title="این تراکنش قبلاً تأیید شده است",
                amount=payment.amount,
                authority=authority,
                body_html='<div class="status done">پرداخت با موفقیت ثبت شده بود.</div>',
                show_form=False,
            )
        if payment.status == PaymentStatus.FAILED:
            return _render_page(
                title="این تراکنش بسته شده است",
                amount=payment.amount,
                authority=authority,
                body_html=(
                    '<div class="status dead">تراکنش ناموفق/لغوشده است. '
                    "برای پرداخت مجدد از اول فرآیند مشارکت را شروع کنید.</div>"
                ),
                show_form=False,
            )
        return _render_page(
            title="تأیید مشارکت در حرکت",
            amount=payment.amount,
            authority=authority,
            campaign_title=payment.participation.campaign.title,
            body_html="",
            show_form=True,
        )

    @extend_schema(exclude=True)
    def post(self, request: HttpRequest, authority: str) -> HttpResponse:
        payment = self._get_payment(authority)
        if payment is None:
            return self._render_not_found(authority)
        action = (request.POST.get("action") or "").strip().lower()
        callback = _build_callback_url()

        if action == "confirm":
            # marker فقط روی تراکنشِ هنوز-PENDING نوشته می‌شود (self
            # select_for_update + double-check داخل service)؛ اگر race با
            # sweep انقضا/لغو رخ داده باشد False برمی‌گردد و کاربر در
            # callback نتیجهٔ واقعی را می‌بیند.
            confirmed = services.confirm_sandbox_payment(payment=payment)
            if not confirmed:
                payment.refresh_from_db()
                logger.info(
                    "madadkar.sandbox: confirm ignored, payment not confirmable "
                    "payment_id=%s status=%s",
                    payment.pk,
                    payment.status,
                )
            else:
                logger.info(
                    "madadkar.sandbox: payment approved payment_id=%s amount=%s",
                    payment.pk,
                    payment.amount,
                )
            # مثل درگاه واقعی: مرورگر کاربر را با Status=OK به callback
            # می‌فرستیم؛ همان‌جا verify (با بررسی همین marker) انجام می‌شود.
            return self._redirect_to_callback(callback, authority, "OK")

        if action == "cancel":
            return self._redirect_to_callback(callback, authority, "NOK")

        return _render_page(
            title="درخواست نامعتبر",
            amount=payment.amount,
            authority=authority,
            body_html=(
                '<div class="status dead">دکمهٔ معتبری ارسال نشد؛ '
                "لطفاً از دکمه‌های صفحه استفاده کنید.</div>"
            ),
            show_form=True,
        )

    @staticmethod
    def _redirect_to_callback(callback: str, authority: str, status_value: str) -> HttpResponse:
        query = urlencode({"authority": authority, "status": status_value})
        return HttpResponseRedirect(f"{callback}?{query}")

    @staticmethod
    def _get_payment(authority: str) -> Payment | None:
        return (
            Payment.objects.select_related("participation", "participation__campaign")
            .filter(authority=authority, gateway_name="sandbox")
            .first()
        )

    @staticmethod
    def _render_not_found(authority: str) -> HttpResponse:
        return _render_page(
            title="تراکنش یافت نشد",
            amount=None,
            authority=authority,
            body_html=(
                '<div class="status dead">تراکنش sandbox معتبری با این کد رهگیری وجود ندارد.</div>'
            ),
            show_form=False,
            status_code=404,
        )
