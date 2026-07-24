# Generated manually: make R4J field visibility admin safer with typed choices.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("r4j", "0007_report_resource_suggestions"),
    ]

    operations = [
        migrations.AlterField(
            model_name="r4jcriminalfieldvisibility",
            name="field_name",
            field=models.CharField(
                choices=[
                    ("national_code", "کد ملی"),
                    ("birth_date", "تاریخ تولد"),
                    ("gender", "جنسیت"),
                    ("country", "کشور"),
                    ("province", "استان"),
                    ("city", "شهر"),
                    ("description", "توضیحات"),
                    ("crimes_summary", "خلاصه جرائم"),
                    ("other_info", "سایر اطلاعات"),
                ],
                help_text="فیلدی از پروفایل مجرم که نمایش عمومی آن برای همین مجرم override می‌شود.",
                max_length=50,
                verbose_name="فیلد اطلاعاتی",
            ),
        ),
        migrations.AlterField(
            model_name="r4jcriminalfieldvisibility",
            name="is_public",
            field=models.BooleanField(
                default=True,
                help_text="اگر خاموش باشد، این فیلد در خروجی عمومی برای این مجرم مخفی می‌شود.",
                verbose_name="در سایت نمایش داده شود؟",
            ),
        ),
    ]
