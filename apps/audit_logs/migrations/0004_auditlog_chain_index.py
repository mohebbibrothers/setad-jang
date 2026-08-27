"""
Add a unique chain position to audit logs.

این مایگریشن دو مشکل را حل می‌کند:

۱. **انشعاب زنجیره تحت همزمانی.** پیش‌تر هر insert سر زنجیره را بدون قفل
   می‌خواند؛ دو نویسنده‌ی همزمان می‌توانستند یک previous_hash را بردارند و
   زنجیره را دو شاخه کنند. چون event_hash دو رکورد متفاوت بود، constraint
   موجود جلوی آن را نمی‌گرفت و tamper-evidence بی‌صدا از بین می‌رفت.
   ایندکس یکتای `chain_index` این حالت را از نظر ساختاری غیرممکن می‌کند.

۲. **هزینه‌ی نوشتن.** پیدا کردن سر زنجیره با
   `ORDER BY created_at DESC, id DESC LIMIT 1` هیچ ایندکس مناسبی نداشت و روی
   بزرگ‌ترین جدول سیستم به sort کامل تبدیل می‌شد.

backfill دقیقاً با همان ترتیبی انجام می‌شود که زنجیره‌ی موجود بر اساس آن
بسته شده (`created_at`, `id`)، بنابراین هیچ هشی بازمحاسبه نمی‌شود و
`verify_audit_chain_integrity` برای داده‌ی موجود همچنان سبز می‌ماند.
"""

from django.db import migrations, models

BACKFILL_BATCH_SIZE = 2000


def backfill_chain_index(apps, schema_editor):
    """پر کردن chain_index برای رکوردهای موجود با حفظ ترتیب فعلی زنجیره."""
    AuditLog = apps.get_model("audit_logs", "AuditLog")
    db_alias = schema_editor.connection.alias

    queryset = AuditLog.objects.using(db_alias).order_by("created_at", "id").only("id")
    position = 0
    batch = []

    for record in queryset.iterator(chunk_size=BACKFILL_BATCH_SIZE):
        position += 1
        record.chain_index = position
        batch.append(record)
        if len(batch) >= BACKFILL_BATCH_SIZE:
            AuditLog.objects.using(db_alias).bulk_update(batch, ["chain_index"])
            batch = []

    if batch:
        AuditLog.objects.using(db_alias).bulk_update(batch, ["chain_index"])


def clear_chain_index(apps, schema_editor):
    """بازگرداندن chain_index به NULL برای rollback بی‌خطر."""
    AuditLog = apps.get_model("audit_logs", "AuditLog")
    AuditLog.objects.using(schema_editor.connection.alias).update(chain_index=None)


class Migration(migrations.Migration):
    """Introduce the unique, index-backed audit chain position."""

    dependencies = [
        ("audit_logs", "0003_auditlog_event_hash_auditlog_hash_version_and_more"),
    ]

    operations = [
        # گام ۱: ستون بدون constraint یکتا اضافه می‌شود تا backfill بتواند اجرا شود.
        migrations.AddField(
            model_name="auditlog",
            name="chain_index",
            field=models.BigIntegerField(blank=True, null=True, verbose_name="موقعیت در زنجیره"),
        ),
        # گام ۲: مقداردهی رکوردهای موجود با ترتیب فعلی زنجیره.
        migrations.RunPython(backfill_chain_index, clear_chain_index),
        # گام ۳: حالا که مقادیر یکتا هستند، constraint یکتا اعمال می‌شود.
        migrations.AlterField(
            model_name="auditlog",
            name="chain_index",
            field=models.BigIntegerField(blank=True, null=True, unique=True, verbose_name="موقعیت در زنجیره"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["-created_at"], name="audit_created_at_desc_idx"),
        ),
    ]
