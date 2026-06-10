"""
Data migration — move Profile.phone_number to User.phone_number.

این migration:
- برای هر Profile با phone_number پر، آن مقدار را به User.phone_number کپی می‌کند
  فقط اگر User.phone_number قبلاً خالی باشد (تا overwrite اتفاق نیفتد).
- در این مرحله مقدار raw کپی می‌شود؛ normalize به فرمت E.164 در Phase C
  انجام خواهد شد.
- در صورت تداخل (مثلاً دو Profile با شماره‌ی یکسان روی دو User مختلف، که
  حالا با unique=True سازگار نیست)، فقط اولین مورد منتقل می‌شود و بقیه
  لاگ می‌شوند تا قابل بررسی دستی باشند.

Reversibility:
- این migration backward قابل reverse است (operation معکوس آن یک no-op است
  چون داده در Profile دست‌نخورده باقی می‌ماند تا migration بعدی schema
  cleanup انجام دهد).
"""

from __future__ import annotations

import logging

from django.db import migrations


logger = logging.getLogger("apps.authentication.migrations")


def move_phone_numbers(apps, schema_editor):
    """انتقال phone_number از Profile به User (فقط برای رکوردهای خالی در User)."""
    Profile = apps.get_model("authentication", "Profile")
    User = apps.get_model("authentication", "User")

    profiles_with_phone = Profile.objects.exclude(phone_number="").select_related("user")
    moved = 0
    skipped_already_has_user_phone = 0
    skipped_duplicate = 0

    used_phones: set[str] = set(
        User.objects.exclude(phone_number__isnull=True).values_list(
            "phone_number", flat=True
        )
    )

    for profile in profiles_with_phone.iterator():
        user = profile.user
        candidate = (profile.phone_number or "").strip()
        if not candidate:
            continue

        if user.phone_number:
            skipped_already_has_user_phone += 1
            continue

        if candidate in used_phones:
            logger.warning(
                "Phone migration: duplicate phone_number=%s detected for user_id=%s; skipping.",
                candidate,
                user.pk,
            )
            skipped_duplicate += 1
            continue

        user.phone_number = candidate
        user.save(update_fields=["phone_number"])
        used_phones.add(candidate)
        moved += 1

    logger.info(
        "Phone migration finished: moved=%d, skipped_already_has=%d, skipped_duplicate=%d",
        moved,
        skipped_already_has_user_phone,
        skipped_duplicate,
    )


def noop_reverse(apps, schema_editor):
    """No-op reverse: داده در Profile دست‌نخورده باقی می‌ماند تا migration بعدی schema را پاک کند."""
    return


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0002_add_phone_identifier_fields"),
    ]

    operations = [
        migrations.RunPython(
            code=move_phone_numbers,
            reverse_code=noop_reverse,
            atomic=True,
        ),
    ]