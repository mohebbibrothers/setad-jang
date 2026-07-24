# Generated manually: typed R4J report suggestions for aliases, contacts, socials, and evidence promotion.

import django.db.models.deletion
import apps.r4j.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("r4j", "0006_remove_investigation_cases"),
    ]

    operations = [
        migrations.AddField(
            model_name="r4jreportattachment",
            name="admin_note",
            field=models.TextField(blank=True, verbose_name="یادداشت ادمین"),
        ),
        migrations.AddField(
            model_name="r4jreportattachment",
            name="promoted_criminal_attachment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="source_report_attachments",
                to="r4j.r4jcriminalattachment",
                verbose_name="سند رسمی ساخته‌شده",
            ),
        ),
        migrations.AddField(
            model_name="r4jreportattachment",
            name="status",
            field=models.CharField(
                choices=[("pending", "در انتظار بررسی"), ("approved", "تأیید شده"), ("rejected", "رد شده")],
                default="pending",
                max_length=20,
                verbose_name="وضعیت بررسی",
            ),
        ),
        migrations.CreateModel(
            name="R4JReportAliasSuggestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاریخ بروزرسانی")),
                ("is_active", models.BooleanField(default=True, verbose_name="فعال")),
                ("alias", models.CharField(max_length=200, verbose_name="نام مستعار پیشنهادی")),
                ("status", models.CharField(choices=[("pending", "در انتظار بررسی"), ("approved", "تأیید شده"), ("rejected", "رد شده")], default="pending", max_length=20, verbose_name="وضعیت")),
                ("admin_note", models.TextField(blank=True, verbose_name="یادداشت ادمین")),
                ("applied_alias", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="source_report_suggestions", to="r4j.r4jcriminalalias", verbose_name="نام مستعار اعمال‌شده")),
                ("report", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="alias_suggestions", to="r4j.r4jreport", verbose_name="گزارش")),
            ],
            options={"verbose_name": "پیشنهاد نام مستعار", "verbose_name_plural": "پیشنهادهای نام مستعار", "ordering": ["report_id", "id"]},
        ),
        migrations.CreateModel(
            name="R4JReportPhoneSuggestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاریخ بروزرسانی")),
                ("is_active", models.BooleanField(default=True, verbose_name="فعال")),
                ("label", models.CharField(blank=True, max_length=50, verbose_name="برچسب")),
                ("number", models.CharField(max_length=30, validators=[apps.r4j.validators.validate_phone_number], verbose_name="شماره پیشنهادی")),
                ("is_public", models.BooleanField(default=False, verbose_name="پیشنهاد نمایش عمومی")),
                ("notes", models.TextField(blank=True, verbose_name="توضیحات")),
                ("status", models.CharField(choices=[("pending", "در انتظار بررسی"), ("approved", "تأیید شده"), ("rejected", "رد شده")], default="pending", max_length=20, verbose_name="وضعیت")),
                ("admin_note", models.TextField(blank=True, verbose_name="یادداشت ادمین")),
                ("applied_phone", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="source_report_suggestions", to="r4j.r4jcriminalphone", verbose_name="شماره اعمال‌شده")),
                ("report", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="phone_suggestions", to="r4j.r4jreport", verbose_name="گزارش")),
            ],
            options={"verbose_name": "پیشنهاد شماره تماس", "verbose_name_plural": "پیشنهادهای شماره تماس", "ordering": ["report_id", "id"]},
        ),
        migrations.CreateModel(
            name="R4JReportSocialSuggestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاریخ بروزرسانی")),
                ("is_active", models.BooleanField(default=True, verbose_name="فعال")),
                ("platform", models.CharField(choices=[("telegram", "تلگرام"), ("twitter_x", "توییتر / ایکس"), ("instagram", "اینستاگرام"), ("linkedin", "لینکدین"), ("facebook", "فیسبوک"), ("tiktok", "تیک‌تاک"), ("truth_social", "تروث سوشال"), ("youtube", "یوتیوب"), ("website", "وب‌سایت"), ("other", "سایر")], max_length=20, verbose_name="پلتفرم")),
                ("handle_or_url", models.CharField(max_length=255, verbose_name="هندل یا URL پیشنهادی")),
                ("is_public", models.BooleanField(default=True, verbose_name="پیشنهاد نمایش عمومی")),
                ("status", models.CharField(choices=[("pending", "در انتظار بررسی"), ("approved", "تأیید شده"), ("rejected", "رد شده")], default="pending", max_length=20, verbose_name="وضعیت")),
                ("admin_note", models.TextField(blank=True, verbose_name="یادداشت ادمین")),
                ("applied_social", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="source_report_suggestions", to="r4j.r4jcriminalsocial", verbose_name="شبکه اجتماعی اعمال‌شده")),
                ("report", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="social_suggestions", to="r4j.r4jreport", verbose_name="گزارش")),
            ],
            options={"verbose_name": "پیشنهاد شبکه اجتماعی", "verbose_name_plural": "پیشنهادهای شبکه اجتماعی", "ordering": ["report_id", "id"]},
        ),
        migrations.AddIndex(model_name="r4jreportaliassuggestion", index=models.Index(fields=["report", "status"], name="r4j_alias_sug_rep_stat_idx")),
        migrations.AddIndex(model_name="r4jreportphonesuggestion", index=models.Index(fields=["report", "status"], name="r4j_phone_sug_rep_stat_idx")),
        migrations.AddIndex(model_name="r4jreportphonesuggestion", index=models.Index(fields=["number"], name="r4j_phone_sug_number_idx")),
        migrations.AddIndex(model_name="r4jreportsocialsuggestion", index=models.Index(fields=["report", "status"], name="r4j_soc_sug_rep_stat_idx")),
        migrations.AddIndex(model_name="r4jreportsocialsuggestion", index=models.Index(fields=["platform"], name="r4j_soc_sug_platform_idx")),
    ]
