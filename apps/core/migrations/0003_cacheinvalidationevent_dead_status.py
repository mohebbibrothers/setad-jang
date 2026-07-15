# Generated for cache invalidation outbox hardening.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_cacheinvalidationevent"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cacheinvalidationevent",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("processing", "Processing"),
                    ("succeeded", "Succeeded"),
                    ("failed", "Failed"),
                    ("dead", "Dead"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
    ]
