"""
Factories اپ احراز هویت.

این ماژول factoryهای مرتبط با کاربر را تعریف می‌کند:
- UserFactory: کاربر عادی فعال
- AdminUserFactory: کاربر ادمین فعال (با role=admin و is_staff=True)

اصول طراحی:
- پسوردها واقعی hash می‌شوند (PostGenerated) تا login واقعی هم تست‌پذیر باشد.
- ایمیل‌ها از Faker با sequence یکتا تولید می‌شوند تا collision نداشته باشیم.
- هیچ assertion یا business logic داخل factories نیست؛ فقط ساخت داده.
"""

from __future__ import annotations

import factory
from django.contrib.auth import get_user_model
from factory.django import DjangoModelFactory

User = get_user_model()


class UserFactory(DjangoModelFactory):
    """Factory برای ساخت کاربر عادی فعال در تست‌ها."""

    class Meta:
        model = User
        django_get_or_create = ("email",)
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user-{n}@test.local")
    is_active = True
    is_staff = False
    is_superuser = False

    @factory.post_generation
    def password(obj, create: bool, extracted: str | None, **kwargs) -> None:
        """
        تنظیم پسورد به‌صورت hashed.

        اگر extracted بدهیم، همان پسورد ست می‌شود؛ در غیر این صورت
        یک پسورد قوی پیش‌فرض ست می‌شود تا تست‌های login بدون درگیری کار کنند.
        """
        if not create:
            return

        raw_password = extracted or "StrongPass!234"
        obj.set_password(raw_password)
        obj.save(update_fields=["password"])


class AdminUserFactory(UserFactory):
    """Factory برای ساخت کاربر ادمین فعال با دسترسی staff/superuser."""

    email = factory.Sequence(lambda n: f"admin-{n}@test.local")
    is_staff = True
    is_superuser = True

    @factory.post_generation
    def role(obj, create: bool, extracted: str | None, **kwargs) -> None:
        """
        تنظیم role روی admin اگر مدل User فیلد role داشته باشد.

        پروژه از custom User با role استفاده می‌کند، ولی این factory
        defensive نوشته شده تا اگر روزی این فیلد حذف شد هم نشکند.
        """
        if not create:
            return

        if hasattr(obj, "role"):
            obj.role = "admin"
            obj.save(update_fields=["role"])
