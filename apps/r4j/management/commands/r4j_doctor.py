"""r4j_doctor — چرا بخشِ «جایزه‌ای برای عدالت» عدد/اطلاعات نشان نمی‌دهد؟

چرا این دستور وجود دارد
------------------------
روی استقرارِ واقعی، صفحهٔ `/r4j` پرونده‌ها را نشان می‌داد ولی همهٔ کارت‌ها
«بدون جایزهٔ فعال» بودند، در حالی که سربرگِ همان صفحه می‌گفت «بیشترین جایزهٔ
فعال روی یک پرونده ۵۰٬۰۰۰ تومان». یعنی داده وجود داشت و نمایش نمی‌شد.

دلیلِ ساختاری: `R4JCriminal.total_bounty_toman` و `bounties_count` فیلدهای
**denormalized** هستند؛ فقط وقتی سرویس‌های اپ bounty را تغییر می‌دهند sync
می‌شوند. هر ورودِ داده از بیرونِ آن مسیرها (ایمپورت، SQLِ دستی، انتقالِ دیتا
از هاستِ قبلی، یا اجرای مایگریشن پیش از ورودِ داده) این دو عدد را صفر
باقی می‌گذارد؛ نتیجه: کارت‌ها «بدون جایزهٔ فعال» و مرتب‌سازیِ «بیشترین جایزه»
بی‌اثر می‌شود.

این دستور همین را قابلِ دیدن و قابلِ اصلاح می‌کند:

    <venv>/python manage.py r4j_doctor              # تشخیص (فقط‌خواندنی)
    <venv>/python manage.py r4j_doctor --fix        # بازمحاسبهٔ شمارنده‌ها
    <venv>/python manage.py r4j_doctor --fix --dry-run

بررسی‌ها
    1  سرشماریِ پرونده‌ها (منتشرشده / پیش‌نویس) و bountyها به تفکیکِ وضعیت
    2  مقایسهٔ عددِ ذخیره‌شده با عددِ واقعیِ محاسبه‌شده از ردیف‌های bounty
    3  پرونده‌هایی که عکسِ اصلی ندارند یا فایلِ عکسشان روی دیسک نیست
    4  اصلاح: همان فرمولِ سرویس (`BOUNTY_ACTIVE_STATUSES`) دوباره اعمال می‌شود
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Count, Sum

from apps.r4j.choices import BOUNTY_ACTIVE_STATUSES
from apps.r4j.models import R4JBounty, R4JCriminal, R4JCriminalPhoto


class Command(BaseCommand):
    """تشخیص و اصلاحِ شمارنده‌های denormalized بخشِ R4J."""

    help = (
        "وضعیتِ دادهٔ بخشِ «جایزه‌ای برای عدالت» را می‌سنجد (پرونده‌ها، bountyها، "
        "شمارنده‌های ذخیره‌شده، عکس‌ها) و با --fix شمارنده‌ها را بازمحاسبه می‌کند."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--fix", action="store_true", help="شمارنده‌های criminal را بازمحاسبه کن"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="با --fix: فقط نشان بده چه تغییر می‌کند"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        out = self.stdout
        problems = 0

        # ---------------------------------------------------------- 1 census
        out.write("=== ۱) سرشماری ===")
        total_criminals = R4JCriminal.all_objects.count()
        published = R4JCriminal.objects.count()  # manager پیش‌فرض = منتشرشده‌ها
        out.write(f"  پرونده‌ها: {total_criminals} (منتشرشده: {published})")
        if published == 0:
            out.write("  [!!] هیچ پروندهٔ منتشرشده‌ای نیست — صفحه عمومی خالی می‌ماند.")
            problems += 1

        bounties = R4JBounty.objects.values("status").annotate(
            n=Count("id"), total=Sum("amount_toman")
        )
        bounty_rows = {row["status"]: (row["n"], row["total"] or 0) for row in bounties}
        if not bounty_rows:
            out.write("  [!!] هیچ bounty‌ای در دیتابیس نیست — همهٔ کارت‌ها «بدون جایزهٔ فعال» می‌شوند.")
            problems += 1
        for status, (count, amount) in sorted(bounty_rows.items()):
            counted = "شمرده می‌شود" if status in BOUNTY_ACTIVE_STATUSES else "شمرده نمی‌شود"
            out.write(f"  bounty[{status}]: {count} ردیف، {amount:,} تومان ({counted})")

        # ------------------------------------------------- 2 counter mismatch
        out.write("")
        out.write("=== ۲) شمارنده‌های ذخیره‌شده در برابر واقعیت ===")
        live_rows = (
            R4JBounty.objects.filter(status__in=BOUNTY_ACTIVE_STATUSES)
            .values("criminal_id")
            .annotate(total=Sum("amount_toman"), cnt=Count("id"))
        )
        live = {row["criminal_id"]: (row["total"] or 0, row["cnt"] or 0) for row in live_rows}

        mismatches: list[tuple[R4JCriminal, int, int, int, int]] = []
        for criminal in R4JCriminal.all_objects.only(
            "id", "first_name", "last_name", "total_bounty_toman", "bounties_count", "is_published"
        ).iterator():
            actual_total, actual_count = live.get(criminal.pk, (0, 0))
            if (
                criminal.total_bounty_toman != actual_total
                or criminal.bounties_count != actual_count
            ):
                mismatches.append(
                    (
                        criminal,
                        criminal.total_bounty_toman,
                        criminal.bounties_count,
                        actual_total,
                        actual_count,
                    )
                )

        if mismatches:
            out.write(
                f"  [!!] {len(mismatches)} پرونده شمارندهٔ نادرست دارد "
                "(کارت‌شان «بدون جایزهٔ فعال» دیده می‌شود):"
            )
            for criminal, stored_total, stored_count, actual_total, actual_count in mismatches[:15]:
                out.write(
                    f"       {criminal.first_name} {criminal.last_name}: "
                    f"ذخیره={stored_total:,}/{stored_count}  واقعی={actual_total:,}/{actual_count}"
                )
            problems += 1
        else:
            out.write("  [OK] همهٔ شمارنده‌ها با واقعیت هم‌خوان‌اند")

        # ------------------------------------------------------ 3 photos
        out.write("")
        out.write("=== ۳) عکس‌های پرونده‌ها ===")
        missing_photo = []
        missing_file = []
        for criminal in R4JCriminal.objects.only("id", "first_name", "last_name").iterator():
            photo = R4JCriminalPhoto.objects.filter(criminal=criminal).order_by("id").first()
            if photo is None:
                missing_photo.append(criminal)
                continue
            try:
                if photo.image and not photo.image.storage.exists(photo.image.name):
                    missing_file.append((criminal, photo.image.name))
            except Exception:
                missing_file.append((criminal, getattr(photo.image, "name", "?")))

        if missing_photo:
            out.write(f"  [--] {len(missing_photo)} پروندهٔ منتشرشده بدونِ هیچ عکس است")
        if missing_file:
            out.write(f"  [!!] {len(missing_file)} فایلِ عکس روی دیسک نیست:")
            for criminal, name in missing_file[:10]:
                out.write(f"       {criminal.first_name} {criminal.last_name}: {name}")
            out.write(
                "       رفع: <venv>/python scripts/media_audit.py --restore-from <media tarball> --apply"
            )
            problems += 1
        if not missing_photo and not missing_file:
            out.write("  [OK] همهٔ عکس‌های ارجاع‌شده موجودند")

        # -------------------------------------------------------- 4 fix
        out.write("")
        if options["fix"]:
            out.write("=== ۴) بازمحاسبه ===")
            if options["dry_run"]:
                out.write(f"  [dry] {len(mismatches)} پرونده به‌روز می‌شد")
            else:
                updated = 0
                for criminal, *_ in mismatches:
                    actual_total, actual_count = live.get(criminal.pk, (0, 0))
                    R4JCriminal.all_objects.filter(pk=criminal.pk).update(
                        total_bounty_toman=actual_total,
                        bounties_count=actual_count,
                    )
                    updated += 1
                out.write(f"  [OK] شمارندهٔ {updated} پرونده بازمحاسبه شد")
                if updated:
                    out.write(
                        "  حالا /r4j را رفرش کنید؛ مبالغ و مرتب‌سازیِ «بیشترین جایزه» کار می‌کند."
                    )
        else:
            out.write("=== ۴) اصلاح ===")
            if mismatches:
                out.write("  برای اصلاح: manage.py r4j_doctor --fix")
            else:
                out.write("  چیزی برای اصلاح نیست")

        out.write("")
        out.write("============================================================")
        if problems == 0:
            out.write(" RESULT: دادهٔ R4J سالم است")
        else:
            out.write(f" RESULT: {problems} مورد نیازِ رسیدگی دارد (بالا را ببینید)")
        out.write("============================================================")
