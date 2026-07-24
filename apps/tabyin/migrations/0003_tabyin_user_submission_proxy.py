from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tabyin", "0002_user_submission_workflow"),
    ]

    operations = [
        migrations.CreateModel(
            name="TabyinUserSubmission",
            fields=[],
            options={
                "verbose_name": "ارسال کاربر تبیین",
                "verbose_name_plural": "ارسال‌های کاربران تبیین",
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("tabyin.tabyincontent",),
        ),
    ]
