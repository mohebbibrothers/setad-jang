"""
Factories اپ تبیین.

این ماژول factoryهای مرتبط با محتوای تبیین را تعریف می‌کند:
- TabyinContentFactory: ساخت یک محتوای تبیین فعال و سالم
- TabyinAttachmentFactory: ساخت یک پیوست متصل به محتوا

اصول طراحی:
- مقادیر باید همیشه یکتا و قابل پیش‌بینی باشند تا تست‌ها flaky نشوند.
- روابط (FK) به‌صورت SubFactory مدیریت می‌شوند تا تست‌ها سبک بمانند.
- attachment به‌صورت پیش‌فرض ساخته نمی‌شود؛ هر تست در صورت نیاز
  خودش attachment لازم را می‌سازد.
- content_hash به‌صورت deterministic از external_id محاسبه می‌شود
  تا sync engine هم در تست‌ها قابل اتکا بماند.
"""

from __future__ import annotations

import hashlib

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.tabyin.choices import MediaType
from apps.tabyin.models import TabyinAttachment, TabyinContent


def _hash_for(external_id: str) -> str:
    """
    تولید یک content_hash deterministic از external_id.

    در محیط واقعی این مقدار از فیلدهای محتوا ساخته می‌شود؛ ولی برای تست
    کافی است مقدار قابل پیش‌بینی و یکتا باشد.
    """
    return hashlib.sha256(external_id.encode("utf-8")).hexdigest()


class TabyinContentFactory(DjangoModelFactory):
    """
    Factory برای ساخت محتوای تبیین فعال و قابل نمایش به صورت پیش‌فرض.

    فقط فیلدهای ضروری/معنادار پر می‌شوند؛ بقیه‌ی فیلدها از default
    خود مدل استفاده می‌کنند تا تست‌ها سبک و خوانا بمانند.
    """

    class Meta:
        model = TabyinContent
        django_get_or_create = ("external_id",)

    external_id = factory.Sequence(lambda n: f"ext-{n:06d}")
    title = factory.Faker("sentence", nb_words=6)
    description = factory.Faker("paragraph", nb_sentences=3)
    author_username = factory.Faker("user_name")

    source_entity_id = factory.Sequence(lambda n: 1000 + n)
    source_status = 1
    source_type = 1

    source_created_at = factory.LazyFunction(timezone.now)
    source_updated_at = factory.LazyFunction(timezone.now)
    source_url = factory.LazyAttribute(
        lambda obj: f"https://source.example.test/contents/{obj.external_id}/",
    )

    raw_payload = factory.LazyAttribute(
        lambda obj: {
            "id": obj.external_id,
            "title": obj.title,
            "username": obj.author_username,
        },
    )
    content_hash = factory.LazyAttribute(lambda obj: _hash_for(obj.external_id))
    last_synced_at = factory.LazyFunction(timezone.now)

    is_active = True
    is_deleted_in_source = False


class TabyinAttachmentFactory(DjangoModelFactory):
    """
    Factory برای ساخت یک پیوست متصل به یک محتوای تبیین.

    اگر content صریحاً به factory پاس داده نشود، یک TabyinContent جدید
    به صورت SubFactory ساخته می‌شود.
    """

    class Meta:
        model = TabyinAttachment

    content = factory.SubFactory(TabyinContentFactory)
    url = factory.Sequence(
        lambda n: f"https://cdn.example.test/files/{n:06d}.jpg",
    )
    relative_url = factory.LazyAttribute(
        lambda obj: obj.url.replace("https://cdn.example.test", ""),
    )
    media_type = MediaType.IMAGE
    size = "1280X905"
    duration = 0
    file_size = 256
    title = factory.Faker("sentence", nb_words=3)
    order = factory.Sequence(lambda n: n)
