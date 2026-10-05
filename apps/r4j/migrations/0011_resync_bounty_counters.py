"""
ترمیمِ یک‌بارمصرفِ شمارنده‌های صندوق (data migration).

ریشه‌ی باگ: پیش از این، تغییرِ وضعیتِ تعهد از داخلِ Django Admin (ادیتِ
مستقیمِ فیلد status) ممکن بود؛ آن مسیر services.approve/reject_bounty_cancel
را اجرا نمی‌کرد، پس ``_sync_criminal_bounty_counters`` هم اجرا نمی‌شد و
total_bounty_toman / bounties_count روی R4JCriminal برای همیشه توسط
تعهدِ لغوشده باد می‌ماند.

این مایگریشن، یک‌بار، شمارنده‌های همه‌ی پرونده‌ها را با همان قراردادِ
service layer دوباره محاسبه می‌کند: فقط تعهد‌های active و cancel_requested
در صندوق و شمارشِ «تعهد‌های ثبت‌شده» حساب می‌شوند؛ canceled خارج است.

- idempotent است؛ اجرای دوباره هزینه ندارد (فقط ردیف‌های ناهماهنگ update می‌شوند).
- از queryset.update استفاده می‌کنیم تا سیگنال‌ها بی‌دلیل فایر نشوند؛
  کشِ عمومی با TTL خودش تازه می‌شود.
- بازگشت (reverse) معنایی ندارد: «درست» بازمحاسبه‌شده هر طرفِ قضیه است.
"""

from __future__ import annotations

from django.db import migrations
from django.db.models import Count, Sum

#: آینه‌ی BOUNTY_ACTIVE_STATUSES در choices.py — به‌صورت literal تا
#: مایگریشن به کدِ فعلیِ اپلیکیشن جفت نشود (اصولِ migration snapshot).
COUNTED_STATUSES = ("active", "cancel_requested")


def resync_bounty_counters(apps, schema_editor):
    """بازمحاسبه‌ی total_bounty_toman و bounties_count برای همه‌ی پرونده‌ها."""
    Criminal = apps.get_model("r4j", "R4JCriminal")
    Bounty = apps.get_model("r4j", "R4JBounty")

    live_rows = Bounty.objects.filter(status__in=COUNTED_STATUSES).values("criminal_id").annotate(
        total=Sum("amount_toman"),
        cnt=Count("id"),
    )
    live = {row["criminal_id"]: (row["total"] or 0, row["cnt"] or 0) for row in live_rows}

    resynced = 0
    for criminal in Criminal.objects.all().iterator():
        total, cnt = live.get(criminal.pk, (0, 0))
        if criminal.total_bounty_toman != total or criminal.bounties_count != cnt:
            Criminal.objects.filter(pk=criminal.pk).update(
                total_bounty_toman=total,
                bounties_count=cnt,
            )
            resynced += 1

    if resynced:
        print(f"\n  r4j 0011: bounty counters resynced for {resynced} criminal(s).")


class Migration(migrations.Migration):
    dependencies = [
        ("r4j", "0010_search_gin_indexes"),
    ]

    operations = [
        migrations.RunPython(resync_bounty_counters, migrations.RunPython.noop),
    ]
