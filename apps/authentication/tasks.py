"""Celery tasks for authentication maintenance and token hygiene."""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

logger = logging.getLogger(__name__)

#: تعداد ردیفی که در هر رفت‌وبرگشت حذف می‌شود. عمداً کوچک است تا هر DELETE
#: کوتاه بماند و روی جدولی که مسیر احراز هویت به آن وابسته است قفل طولانی
#: ایجاد نشود.
FLUSH_BATCH_SIZE = 1_000

#: سقف تعداد batch در هر اجرا. با زمان‌بندی ساعتی یعنی حداکثر ۱۰۰ هزار ردیف
#: در ساعت پاک می‌شود که برای هر نرخ تولید واقعی کافی است، و در عین حال یک
#: اجرای منفرد نمی‌تواند بی‌نهایت طول بکشد یا worker را اشغال کند.
FLUSH_MAX_BATCHES = 100


@shared_task(
    name="apps.authentication.tasks.flush_expired_jwt_tokens_task",
    ignore_result=False,
)
def flush_expired_jwt_tokens_task(
    *,
    batch_size: int = FLUSH_BATCH_SIZE,
    max_batches: int = FLUSH_MAX_BATCHES,
) -> dict[str, int]:
    """Delete expired JWT outstanding/blacklisted token rows in bounded batches.

    چرا این تسک لازم است
    ---------------------
    پروژه با ``ROTATE_REFRESH_TOKENS=True`` و ``BLACKLIST_AFTER_ROTATION=True``
    کار می‌کند، یعنی **هر بار refresh** یک ``OutstandingToken`` جدید و یک
    ``BlacklistedToken`` جدید تولید می‌شود. بدون پاک‌سازی، این دو جدول تا ابد
    رشد می‌کنند؛ و چون مسیر احراز هویت در هر درخواست به آن‌ها می‌خورد، نتیجه
    یک کندی تدریجی و بسیار سخت‌تشخیص در کل API است.

    چرا batch و نه ``flushexpiredtokens``
    --------------------------------------
    دستور آمادهٔ simplejwt یک ``DELETE`` بدون کران روی کل ردیف‌های منقضی اجرا
    می‌کند. اولین اجرا روی جدولی که ماه‌ها انباشته شده می‌تواند میلیون‌ها ردیف
    را در یک تراکنش حذف کند: قفل طولانی، رشد انفجاری WAL و در بدترین حالت
    از کار افتادن login در همان بازه. اینجا حذف به قطعات کوچک شکسته شده و هر
    قطعه تراکنش مستقل خودش را دارد.

    ``BlacklistedToken`` با ``on_delete=CASCADE`` به ``OutstandingToken`` وصل
    است، پس حذف والد کافی است؛ شمارش جداگانه فقط برای رصدپذیری انجام می‌شود.

    Returns:
        دیکشنری با تعداد ردیف‌های حذف‌شده و اینکه آیا کار ناتمام مانده است.
    """
    now = timezone.now()
    expired = OutstandingToken.objects.filter(expires_at__lte=now)

    outstanding_label = OutstandingToken._meta.label
    blacklisted_label = BlacklistedToken._meta.label

    deleted_outstanding = 0
    deleted_blacklisted = 0
    exhausted = True

    for _ in range(max_batches):
        pks = list(expired.values_list("pk", flat=True)[:batch_size])
        if not pks:
            break
        _total, per_model = OutstandingToken.objects.filter(pk__in=pks).delete()
        deleted_outstanding += per_model.get(outstanding_label, 0)
        deleted_blacklisted += per_model.get(blacklisted_label, 0)
    else:
        # حلقه بدون break تمام شد، یعنی به سقف batch خوردیم؛ ممکن است هنوز
        # ردیف منقضی باقی مانده باشد و اجرای بعدی باید ادامه دهد.
        exhausted = not expired.exists()

    logger.info(
        "Flushed expired JWT tokens outstanding=%s blacklisted=%s exhausted=%s",
        deleted_outstanding,
        deleted_blacklisted,
        exhausted,
    )
    return {
        "deleted_outstanding": deleted_outstanding,
        "deleted_blacklisted": deleted_blacklisted,
        "exhausted": int(exhausted),
    }
