"""Seed default cross-app notification templates."""

from django.db import migrations


def seed_templates(apps, schema_editor):
    """Seed editable default notification templates."""
    NotificationTemplate = apps.get_model("notifications", "NotificationTemplate")
    rows = [
        ("support.reply", "in_app", "پاسخ جدید پشتیبانی", "تیکت {ticket_number}", "برای تیکت {ticket_number} پاسخ جدید ثبت شد: {message}"),
        ("support.resolved", "in_app", "حل تیکت", "تیکت {ticket_number} حل شد", "تیکت «{subject}» حل شد. در صورت نیاز می‌توانید آن را بازگشایی کنید."),
        ("public_report.status_changed", "in_app", "تغییر وضعیت گزارش", "گزارش {tracking_code}", "وضعیت گزارش شما به {status} تغییر کرد."),
        ("tabyin.submission_approved", "in_app", "تأیید محتوای تبیین", "محتوای شما تأیید شد", "محتوای «{content_title}» تأیید شد."),
        ("tabyin.submission_rejected", "in_app", "رد محتوای تبیین", "محتوای شما رد شد", "محتوای «{content_title}» رد شد."),
        ("madadkar.payment_success", "in_app", "پرداخت موفق", "پرداخت شما ثبت شد", "پرداخت شما برای «{campaign_title}» با کد {ref_id} ثبت شد."),
        ("lms.certificate_issued", "in_app", "صدور مدرک", "مدرک آموزشی صادر شد", "مدرک دوره «{course_title}» با کد {certificate_code} صادر شد."),
        ("kindness.contact_revealed", "in_app", "مشاهده شماره تماس", "شماره تماس آگهی مشاهده شد", "شماره تماس آگهی «{listing_title}» مشاهده شد."),
        ("kindness.high_match", "in_app", "پیشنهاد تطبیق جدید", "تطبیق جدید با امتیاز {score}", "برای آگهی «{listing_title}» یک پیشنهاد تطبیق جدید ثبت شد."),
        ("support.reply", "email", "پاسخ جدید پشتیبانی", "پاسخ جدید برای تیکت {ticket_number}", "برای تیکت {ticket_number} پاسخ جدید ثبت شد:\n{message}"),
        ("lms.certificate_issued", "email", "صدور مدرک", "مدرک دوره {course_title} صادر شد", "مدرک شما با کد {certificate_code} صادر شد."),
        ("madadkar.payment_success", "email", "پرداخت موفق", "پرداخت موفق برای {campaign_title}", "پرداخت شما با کد {ref_id} ثبت شد."),
    ]
    for code, channel, title, subject, body in rows:
        NotificationTemplate.objects.get_or_create(
            code=code,
            channel=channel,
            defaults={"title": title, "subject_template": subject, "body_template": body},
        )


def noop_reverse(apps, schema_editor):
    """Keep templates on reverse to preserve admin edits."""


class Migration(migrations.Migration):
    """Seed editable notification templates."""

    dependencies = [("notifications", "0002_alter_notificationtemplate_code")]

    operations = [migrations.RunPython(seed_templates, noop_reverse)]
