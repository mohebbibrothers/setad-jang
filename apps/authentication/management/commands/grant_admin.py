"""grant_admin — چه کسی واقعاً اجازهٔ ورود و مدیریت در پنل ادمین را دارد؟

چرا این دستور وجود دارد
------------------------
روی استقرارِ واقعی، کاربری با موفقیت وارد `/admin/` شد و صفحهٔ «مدیریت وب‌گاه»
را دید که می‌گفت **«شما اجازهٔ مشاهده یا ویرایش چیزی را ندارید»**. آن پیام یعنی:

    is_staff=True   ← اجازهٔ ورود به پنل دارد (وگرنه فرمِ لاگین ردش می‌کرد)
    is_superuser=False و هیچ group/permission‌ای هم ندارد
    ⇒ ورود موفق، ولی داشبورد خالی

یعنی مشکلِ «ادمین» احرازِ هویت نبود، **مجوز** بود. این دستور همان یک شکاف را
می‌بندد و برای همیشه قابلِ بررسی می‌کند:

    <venv>/python manage.py grant_admin --list
    <venv>/python manage.py grant_admin --email admin@example.com --superuser
    <venv>/python manage.py grant_admin --email x@y.z --staff      # فقط ورود
    <venv>/python manage.py grant_admin --email x@y.z --revoke     # پس‌گرفتن

قراردادها
    - هیچ رمزی خوانده یا چاپ نمی‌شود.
    - عملیات idempotent است (اگر از قبل superuser باشد، فقط گزارش می‌کند).
    - با ``--superuser`` هم ``is_staff`` و هم ``is_superuser`` روشن می‌شوند، چون
      پنل ادمین به هر دو نیاز دارد و جداکردنشان منبعِ همین باگ بود.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """بازبینی و اصلاحِ دسترسیِ پنل ادمین."""

    help = (
        "وضعیتِ دسترسیِ کاربران به پنل ادمین را نشان می‌دهد و می‌تواند کاربری را "
        "staff/superuser کند یا دسترسی‌اش را بگیرد (بدونِ خواندن یا چاپِ رمز)."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--list", action="store_true", help="فهرستِ همهٔ کاربرانِ staff/superuser")
        parser.add_argument("--email", help="ایمیلِ کاربرِ هدف")
        parser.add_argument(
            "--superuser",
            action="store_true",
            help="دسترسیِ کامل: is_staff + is_superuser (پنل ادمین به هر دو نیاز دارد)",
        )
        parser.add_argument(
            "--staff", action="store_true", help="فقط اجازهٔ ورود به پنل (بدونِ مجوزِ تغییر)"
        )
        parser.add_argument("--revoke", action="store_true", help="گرفتنِ هر دو دسترسی")

    def handle(self, *args: Any, **options: Any) -> None:
        User = get_user_model()
        out = self.stdout

        if options["list"] or not any(
            options[key] for key in ("email", "superuser", "staff", "revoke")
        ):
            return self._list(User)

        email = (options.get("email") or "").strip()
        if not email:
            raise CommandError("--email لازم است (یا از --list استفاده کنید).")

        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f"کاربری با ایمیلِ {email!r} پیدا نشد.")

        before = (bool(user.is_staff), bool(user.is_superuser))

        if options["revoke"]:
            user.is_staff = False
            user.is_superuser = False
        elif options["superuser"]:
            user.is_staff = True
            user.is_superuser = True
        elif options["staff"]:
            user.is_staff = True
        else:
            raise CommandError("یکی از --superuser / --staff / --revoke را بدهید (یا --list).")

        user.save(update_fields=["is_staff", "is_superuser"])
        after = (bool(user.is_staff), bool(user.is_superuser))

        if before == after:
            out.write(f"  [--] بدونِ تغییر: {user.email} (staff={after[0]}, superuser={after[1]})")
        else:
            out.write(
                f"  [OK] {user.email}: staff {before[0]}→{after[0]} · superuser {before[1]}→{after[1]}"
            )
        if after[1]:
            out.write("       حالا می‌تواند از /admin/ همهٔ بخش‌ها را ببیند و تغییر دهد.")
        elif after[0]:
            out.write(
                "       فقط اجازهٔ ورود دارد؛ برای دیدنِ بخش‌ها یا باید superuser شود یا "
                "group/permission بگیرد."
            )
        else:
            out.write("       دیگر به پنل ادمین دسترسی ندارد.")

    def _list(self, User: Any) -> None:
        out = self.stdout
        total = User.objects.count()
        staff = User.objects.filter(is_staff=True).count()
        supers = User.objects.filter(is_superuser=True).count()
        out.write("=== دسترسیِ پنل ادمین ===")
        out.write(f"  کاربران: {total} | staff: {staff} | superuser: {supers}")
        if supers == 0:
            out.write("  [!!] هیچ superuser‌ای وجود ندارد — پنل ادمین عملاً خالی می‌ماند.")
            out.write("       رفع: manage.py grant_admin --email <ایمیل> --superuser")
        elif staff > supers:
            out.write(
                f"  [--] {staff - supers} کاربرِ staff بدونِ superuser: وارد می‌شوند ولی داشبوردشان "
                "خالی است («شما اجازهٔ مشاهده یا ویرایش چیزی را ندارید»)."
            )
        for user in User.objects.filter(is_staff=True).order_by("email")[:25]:
            out.write(
                f"    - {user.email:<40} staff={bool(user.is_staff)} "
                f"superuser={bool(user.is_superuser)} active={bool(user.is_active)}"
            )
        out.write("")
        out.write("  مثال: manage.py grant_admin --email admin@example.com --superuser")
