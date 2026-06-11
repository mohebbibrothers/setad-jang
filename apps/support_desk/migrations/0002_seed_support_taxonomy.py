"""Seed dynamic default taxonomy for Support Desk."""

from django.db import migrations
from django.utils.text import slugify


def _seed_slug(value: str, fallback: str) -> str:
    """Build deterministic unicode slug for seed rows."""
    return slugify(value, allow_unicode=True) or fallback


def seed_support_taxonomy(apps, schema_editor):
    """Create editable default departments, tree categories, SLA policies and macros."""
    SupportDepartment = apps.get_model("support_desk", "SupportDepartment")
    SupportCategory = apps.get_model("support_desk", "SupportCategory")
    SupportSLAPolicy = apps.get_model("support_desk", "SupportSLAPolicy")
    SupportTicketType = apps.get_model("support_desk", "SupportTicketType")
    SupportCannedResponse = apps.get_model("support_desk", "SupportCannedResponse")

    department_titles = [
        "پشتیبانی عمومی",
        "فنی",
        "مالی و پرداخت",
        "حساب کاربری و احراز هویت",
        "آموزش / LMS",
        "دیوار مهربانی",
        "مددکار",
        "گزارشات مردمی",
        "تبیین محتوا",
        "امنیت و حریم خصوصی",
        "همکاری و مشارکت",
    ]
    departments = {}
    for order, title in enumerate(department_titles, start=1):
        department, _created = SupportDepartment.objects.get_or_create(
            title=title,
            defaults={"order": order, "slug": _seed_slug(title, f"department-{order}")},
        )
        departments[title] = department

    category_tree = {
        "حساب کاربری و احراز هویت": {
            "حساب کاربری": ["ورود و رمز عبور", "OTP و شماره موبایل", "تغییر اطلاعات پروفایل", "مشکل احراز هویت"],
        },
        "مالی و پرداخت": {
            "پرداخت و مالی": ["پرداخت ناموفق", "پرداخت موفق ولی ثبت‌نشده", "رسید و پیگیری پرداخت", "مغایرت مبلغ", "بازگشت وجه"],
        },
        "فنی": {
            "مشکلات فنی": ["خطای سایت", "خطای API یا اپلیکیشن", "کندی یا قطعی", "مشکل آپلود فایل", "مشکل نمایش صفحه"],
        },
        "آموزش / LMS": {
            "LMS / آموزش": ["ثبت‌نام در دوره", "مشاهده درس‌ها", "آزمون و تلاش مجدد", "مدرک و اعتبارسنجی", "پیشرفت دوره"],
        },
        "دیوار مهربانی": {
            "دیوار مهربانی": ["ثبت آگهی", "تأیید یا رد آگهی", "مشکل شماره تماس", "گزارش آگهی", "مچینگ و پیشنهادها"],
        },
        "مددکار": {
            "مددکار": ["کمپین‌ها", "مشارکت و سهم", "پرداخت مددکار", "رسید پرداخت"],
        },
        "گزارشات مردمی": {
            "گزارشات مردمی": ["ثبت گزارش", "پیگیری وضعیت گزارش", "ضمیمه گزارش"],
        },
        "تبیین محتوا": {
            "تبیین محتوا": ["ارسال محتوا", "مشکل محتوای منتشرشده", "درخواست اصلاح محتوا"],
        },
        "امنیت و حریم خصوصی": {
            "امنیت و حریم خصوصی": ["گزارش آسیب‌پذیری", "سوءاستفاده یا جعل هویت", "درخواست حذف یا اصلاح داده"],
        },
        "همکاری و مشارکت": {
            "پیشنهاد و همکاری": ["پیشنهاد محصولی", "همکاری رسانه‌ای", "همکاری فنی", "سایر"],
        },
    }
    categories = {}
    for department_title, roots in category_tree.items():
        department = departments[department_title]
        for root_order, (root_title, children) in enumerate(roots.items(), start=1):
            root_slug = _seed_slug(root_title, f"root-{department.id}-{root_order}")
            root, _created = SupportCategory.objects.get_or_create(
                department=department,
                parent=None,
                title=root_title,
                defaults={"order": root_order, "slug": root_slug, "path": f"/{root_slug}/", "depth": 0},
            )
            categories[root_title] = root
            for child_order, child_title in enumerate(children, start=1):
                child_slug = _seed_slug(child_title, f"child-{root.id}-{child_order}")
                child, _created = SupportCategory.objects.get_or_create(
                    department=department,
                    parent=root,
                    title=child_title,
                    defaults={
                        "order": child_order,
                        "slug": child_slug,
                        "path": f"{root.path.rstrip('/')}/{child_slug}/",
                        "depth": root.depth + 1,
                    },
                )
                categories[child_title] = child

    sla_definitions = [
        ("پشتیبانی معمولی", None, "normal", "minor", 24 * 60, 72 * 60, 1),
        ("اولویت بالا", None, "high", "major", 8 * 60, 24 * 60, 2),
        ("فوری / بحرانی", None, "urgent", "critical", 2 * 60, 8 * 60, 3),
        ("پرداخت و مالی", departments["مالی و پرداخت"], "high", "major", 4 * 60, 24 * 60, 4),
        ("امنیت و حریم خصوصی", departments["امنیت و حریم خصوصی"], "urgent", "critical", 60, 8 * 60, 5),
    ]
    policies = {}
    for title, department, priority, severity, first_minutes, resolution_minutes, order in sla_definitions:
        policy, _created = SupportSLAPolicy.objects.get_or_create(
            title=title,
            defaults={
                "slug": _seed_slug(title, f"sla-{order}"),
                "department": department,
                "priority": priority,
                "severity": severity,
                "first_response_minutes": first_minutes,
                "resolution_minutes": resolution_minutes,
                "order": order,
            },
        )
        policies[title] = policy

    ticket_types = [
        ("question", "سؤال عمومی", "پشتیبانی عمومی", "پشتیبانی معمولی", "normal", "minor", 1),
        ("technical_issue", "مشکل فنی", "فنی", "اولویت بالا", "high", "major", 2),
        ("account", "حساب کاربری", "حساب کاربری و احراز هویت", "پشتیبانی معمولی", "normal", "major", 3),
        ("payment", "پرداخت و مالی", "مالی و پرداخت", "پرداخت و مالی", "high", "major", 4),
        ("report", "گزارش خطا یا تخلف", "پشتیبانی عمومی", "اولویت بالا", "high", "major", 5),
        ("suggestion", "پیشنهاد", "همکاری و مشارکت", "پشتیبانی معمولی", "low", "minor", 6),
        ("partnership", "همکاری", "همکاری و مشارکت", "پشتیبانی معمولی", "normal", "minor", 7),
        ("security", "امنیت و حریم خصوصی", "امنیت و حریم خصوصی", "امنیت و حریم خصوصی", "urgent", "critical", 8),
        ("other", "سایر", "پشتیبانی عمومی", "پشتیبانی معمولی", "normal", "minor", 9),
    ]
    for code, title, department_title, policy_title, priority, severity, order in ticket_types:
        department = departments[department_title]
        SupportTicketType.objects.get_or_create(
            code=code,
            defaults={
                "title": title,
                "default_department": department,
                "default_category": next((category for category in categories.values() if category.department_id == department.id and category.depth == 0), None),
                "default_priority": priority,
                "default_severity": severity,
                "default_sla_policy": policies[policy_title],
                "order": order,
            },
        )

    canned_responses = [
        ("درخواست اطلاعات بیشتر", "سلام، برای بررسی دقیق‌تر لطفاً جزئیات بیشتری از مشکل و در صورت امکان تصویر یا شماره پیگیری ارسال کنید."),
        ("پیگیری پرداخت", "سلام، لطفاً شماره پیگیری پرداخت، مبلغ و زمان تقریبی تراکنش را ارسال کنید تا تیم مالی بررسی کند."),
        ("ارجاع به تیم فنی", "سلام، موضوع شما به تیم فنی ارجاع شد و نتیجه بررسی از همین تیکت اطلاع‌رسانی می‌شود."),
        ("حل مشکل و درخواست تأیید", "سلام، مشکل اعلام‌شده بررسی و اصلاح شد. لطفاً نتیجه را تأیید کنید تا تیکت بسته شود."),
        ("راهنمای بازیابی حساب", "سلام، برای بازیابی حساب لطفاً از مسیر فراموشی رمز عبور یا ورود با کد تأیید استفاده کنید."),
    ]
    for title, body in canned_responses:
        SupportCannedResponse.objects.get_or_create(title=title, defaults={"body": body})


def unseed_support_taxonomy(apps, schema_editor):
    """Keep seeded taxonomy on reverse migrations to preserve admin changes."""


class Migration(migrations.Migration):
    """Seed migration for default editable Support Desk taxonomy."""

    dependencies = [
        ("support_desk", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_support_taxonomy, unseed_support_taxonomy),
    ]
