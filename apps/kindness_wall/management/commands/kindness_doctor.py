"""kindness_doctor — «آگهی‌های من کجاست؟» با یک دستور، بدون حدس.

چرا این دستور وجود دارد
------------------------
تختهٔ عمومیِ دیوار مهربانی فقط آگهی‌های `published` را نشان می‌دهد
(``KindnessListing.objects.published()``). آگهیِ تازه‌ساخته‌شده با پیش‌فرضِ
``ListingStatus.DRAFT`` ساخته می‌شود و تا اکشنِ «انتشار» اجرا نشود **روی
سایت دیده نمی‌شود** — نه در فهرست، نه در جزئیات، نه در sitemap. نتیجهٔ عملی:
کاربر یک آگهی ثبت می‌کند، صفحه را رفرش می‌کند و فکر می‌کند «آگهی‌ها پریدند».

این دستور همان را در یک نگاه روشن می‌کند:

    <venv>/python manage.py kindness_doctor                 # تشخیص
    <venv>/python manage.py kindness_doctor --publish-drafts # انتشارِ پیش‌نویس‌ها
    <venv>/python manage.py kindness_doctor --publish-drafts --dry-run

بررسی‌ها
    1  سرشماریِ آگهی‌ها به تفکیکِ وضعیت (و اینکه کدام‌ها روی تخته دیده می‌شوند)
    2  تفاوتِ «تعدادِ کل» با «تعدادِ عمومی» + فهرستِ آگهی‌های پنهان با دلیل
    3  آگهی‌های منقضی‌شده‌ای که هنوز published مانده‌اند
    4  تصاویرِ گم‌شده (ردیف هست، فایل نیست)
    5  اکشنِ --publish-drafts: همان کاری که دکمهٔ «انتشار» انجام می‌دهد
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.kindness_wall.choices import ListingStatus
from apps.kindness_wall.models import KindnessListing, KindnessListingImage


class Command(BaseCommand):
    """تشخیص و اصلاحِ وضعیتِ آگهی‌های دیوار مهربانی."""

    help = (
        "می‌گوید چند آگهی در چه وضعیتی است، چرا بعضی روی تخته دیده نمی‌شوند، "
        "و با --publish-drafts پیش‌نویس‌ها را منتشر می‌کند."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--publish-drafts",
            action="store_true",
            help="همهٔ آگهی‌های پیش‌نویس را منتشر کن (مثل دکمهٔ «انتشار» در پنل)",
        )
        parser.add_argument("--dry-run", action="store_true", help="با --publish-drafts: فقط بشمار")

    def handle(self, *args: Any, **options: Any) -> None:
        out = self.stdout
        problems = 0

        # ------------------------------------------------------------ 1 census
        out.write("=== ۱) سرشماریِ آگهی‌ها ===")
        rows = []
        for status in ListingStatus.values:
            count = KindnessListing.all_objects.filter(status=status).count()
            visible = "روی تخته دیده می‌شود" if status == ListingStatus.PUBLISHED else "پنهان"
            rows.append((status, count, visible))
        total = KindnessListing.all_objects.count()
        public = KindnessListing.objects.published().count()
        for status, count, visible in rows:
            out.write(f"  {status:<10} {count:>4}  ({visible})")
        out.write("  ------------------------------------------")
        out.write(f"  کل: {total} | روی تخته: {public}")

        if total and public == 0:
            out.write(
                "  [!!] هیچ آگهیِ منتشرشده‌ای نیست — تختهٔ عمومی خالی است حتی اگر آگهی وجود داشته باشد."
            )
            problems += 1

        # --------------------------------------------------- 2 hidden listings
        hidden = KindnessListing.all_objects.exclude(status=ListingStatus.PUBLISHED).order_by(
            "-created_at"
        )
        hidden_count = hidden.count()
        if hidden_count:
            out.write("")
            out.write(f"=== ۲) {hidden_count} آگهی پنهان (روی سایت دیده نمی‌شوند) ===")
            for listing in hidden[:15]:
                out.write(
                    f"  - [{listing.status}] {listing.pk} · {listing.title[:40]} · "
                    f"ساخته‌شده {listing.created_at:%Y-%m-%d %H:%M}"
                )
            if hidden_count > 15:
                out.write(f"  ... و {hidden_count - 15} موردِ دیگر")
            draft_count = sum(1 for _ in hidden if _.status == ListingStatus.DRAFT)
            if draft_count:
                out.write(
                    f"  [--] {draft_count} پیش‌نویس: تا «انتشار» نشوند روی تخته نمی‌آیند "
                    "(این رفتارِ درست است، نه باگ)."
                )
                out.write("       انتشارِ همه: manage.py kindness_doctor --publish-drafts")

        # ------------------------------------------------------ 3 expired live
        out.write("")
        out.write("=== ۳) آگهی‌های منقضی که هنوز منتشرشده‌اند ===")
        now = timezone.now()
        overdue = KindnessListing.objects.published().filter(
            expires_at__isnull=False, expires_at__lt=now
        )
        overdue_count = overdue.count()
        if overdue_count:
            out.write(f"  [--] {overdue_count} آگهی از تاریخِ انقضا گذشته ولی هنوز روی تخته است")
            out.write("       پاک‌سازیِ خودکار با تسکِ beat انجام می‌شود (اگر beat بالاست).")
        else:
            out.write("  [OK] هیچ آگهیِ منقضی روی تخته نیست")

        # --------------------------------------------------------- 4 images
        out.write("")
        out.write("=== ۴) تصاویر ===")
        missing_file = []
        for image in KindnessListingImage.objects.select_related("listing").only(
            "id", "image", "listing"
        )[:500]:
            try:
                if image.image and not image.image.storage.exists(image.image.name):
                    missing_file.append(image)
            except Exception:
                missing_file.append(image)
        if missing_file:
            out.write(f"  [!!] {len(missing_file)} فایلِ تصویر روی دیسک نیست:")
            for image in missing_file[:10]:
                out.write(
                    f"       listing={image.listing_id} · {getattr(image.image, 'name', '?')}"
                )
            out.write("       رفع: <venv>/python scripts/media_audit.py")
            problems += 1
        else:
            out.write("  [OK] همهٔ تصاویرِ ارجاع‌شده موجودند")

        # ----------------------------------------------------------- 5 action
        out.write("")
        if options["publish_drafts"]:
            out.write("=== ۵) انتشارِ پیش‌نویس‌ها ===")
            drafts = KindnessListing.all_objects.filter(status=ListingStatus.DRAFT)
            count = drafts.count()
            if options["dry_run"]:
                out.write(f"  [dry] {count} آگهی منتشر می‌شد")
            elif count == 0:
                out.write("  پیش‌نویسی وجود ندارد")
            else:
                published_now = 0
                for listing in drafts:
                    listing.status = ListingStatus.PUBLISHED
                    listing.published_at = listing.published_at or now
                    listing.save(update_fields=["status", "published_at", "updated_at"])
                    published_now += 1
                out.write(f"  [OK] {published_now} آگهی منتشر شد")
                out.write("  حالا /kindness-wall را رفرش کنید.")
        else:
            out.write("=== ۵) اصلاح ===")
            draft_left = KindnessListing.all_objects.filter(status=ListingStatus.DRAFT).count()
            if draft_left:
                out.write(
                    f"  برای انتشارِ {draft_left} پیش‌نویس: manage.py kindness_doctor --publish-drafts"
                )
            else:
                out.write("  چیزی برای انتشار نیست")

        out.write("")
        out.write("============================================================")
        if problems == 0:
            out.write(" RESULT: وضعیتِ دیوار مهربانی سالم است")
        else:
            out.write(f" RESULT: {problems} مورد نیازِ رسیدگی دارد (بالا را ببینید)")
        out.write("============================================================")
