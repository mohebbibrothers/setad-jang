"""تست‌های بنیادی مدل‌های دیوار مهربانی v2 — کانال‌ها، slug، کاور، سند جستجو.

این فایل «قرارداد داده» را قفل می‌کند: همان چیزی که سیاست جدید رویش سوار است
(هر آگهی حداقل یک راه تماس؛ نرمال‌سازی خودکار؛ کاورِ همیشه‌موجود).
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.kindness_wall.choices import (
    DEFAULT_LISTING_TTL_DAYS,
    ListingStatus,
    OfferStatus,
    Urgency,
)
from apps.kindness_wall.models import (
    KindnessCategory,
    KindnessListing,
    KindnessListingImage,
    KindnessOffer,
    listing_image_upload_path,
)
from apps.kindness_wall.validators import (
    normalize_contact_handle,
    normalize_contact_phone,
    validate_channel_value,
)
from tests.factories.kindness_wall import (
    KindnessCategoryFactory,
    KindnessListingFactory,
    PublishedNeedListingFactory,
)

pytestmark = pytest.mark.django_db


class TestChannelsContract:
    """رجیستری کانال‌ها و قاعدهٔ «حداقل یکی، حداکثر همه»."""

    def test_registry_covers_all_six_required_channels(self) -> None:
        """هر شش کانالی که سیاست نام می‌برد باید فیلد مدل واقعی داشته باشد."""
        fields = [field for field, *_ in KindnessListing.channel_fields()]
        assert fields == [
            "contact_phone",
            "contact_bale",
            "contact_eitaa",
            "contact_telegram",
            "contact_rubika",
            "contact_instagram",
        ]
        for field in fields:
            assert KindnessListing._meta.get_field(field) is not None

    def test_phone_normalizes_persian_digits_and_intl_prefix(self) -> None:
        """۰۹۱۲... / +۹۸ / ۰۰۹۸ هر سه به فرمت داخلی واحد تبدیل می‌شوند."""
        assert normalize_contact_phone("۰۹۱۲۱۲۳۴۵۶۷") == "09121234567"
        assert normalize_contact_phone("+989121234567") == "09121234567"
        assert normalize_contact_phone("۰۰۹۸ ۹۱۲ ۱۲۳ ۴۵۶۷") == "09121234567"

    def test_handle_normalization_strips_at_domain_and_query(self) -> None:
        """آیدی با @، دامنه یا query هم به خامِ معتبر نرمال می‌شود."""
        assert normalize_contact_handle("@user.name") == "user.name"
        assert normalize_contact_handle("https://t.me/janani/").lower() == "janani"
        assert normalize_contact_handle("https://instagram.com/a.b?igsh=xyz") == "a.b"

    def test_invalid_channel_values_rejected(self) -> None:
        """شکل نامعتبر (کوتاه/شروع‌نابدی‌) باید رد شود."""
        with pytest.raises(ValidationError):
            validate_channel_value(kind="phone", value="12345")
        with pytest.raises(ValidationError):
            validate_channel_value(kind="telegram", value="a")

    def test_publish_without_any_contact_is_blocked_by_clean(self) -> None:
        """قاعده طلایی: بدون راه تماس، حتی اعتبارسنجی مدل هم منتشر نمی‌کند."""
        category = KindnessCategoryFactory()
        listing = KindnessListing.objects.create(
            category=category,
            title="یک نیاز بدون راه تماس",
            description="توضیح کافی بیش از بیست نویسه برای این آگهی تستی",
            status=ListingStatus.PUBLISHED,
        )
        listing.contact_phone = ""
        with pytest.raises(ValidationError) as exc_info:
            listing.clean()
        assert "status" in exc_info.value.message_dict

    def test_draft_may_have_no_contacts(self) -> None:
        """پیش‌نویس آزاد است؛ قاعدهٔ تماس فقط از لحظه انتشار به بعد."""
        listing = KindnessListingFactory(status=ListingStatus.DRAFT, contact_phone="")
        listing.clean()  # نباید خطا بدهد

    def test_saved_values_are_normalized_end_to_end(self) -> None:
        """نرمال‌سازی در save واقعی model اتفاق می‌افتد (نه فقط در سریالایزر)."""
        listing = KindnessListingFactory(
            contact_telegram="https://t.me/Mehrban/", contact_phone="+۹۸۹۱۲۱۱۱۲۲۳۳"
        )
        listing.refresh_from_db()
        assert listing.contact_phone == "09121112233"
        assert listing.contact_telegram == "Mehrban"

    def test_channel_payload_only_contains_filled_and_links(self) -> None:
        """payload عمومی: فقط کانال پرشده + لینک قابل‌کلیک درست."""
        listing = KindnessListingFactory(
            contact_phone="۰۹۱۲۱۲۳۴۵۶۷", contact_eitaa="@eitaa_id", contact_bale=""
        )
        payload = listing.channel_payload()
        kinds = {item["kind"] for item in payload}
        assert kinds == {"phone", "eitaa"}
        phone = next(item for item in payload if item["kind"] == "phone")
        assert phone["link"] == "tel:+989121234567"
        eitaa = next(item for item in payload if item["kind"] == "eitaa")
        assert eitaa["link"] == "https://eitaa.com/eitaa_id"


class TestSlugAndSearchDocument:
    def test_persian_title_generates_unicode_slug(self) -> None:
        listing = PublishedNeedListingFactory(title="کمک به سیل‌زدگان آمل")
        assert listing.slug == "کمک-به-سیلزدگان-آمل"

    def test_duplicate_titles_get_suffixed_slugs(self) -> None:
        first = PublishedNeedListingFactory(title="عنوان مشترک تست")
        second = PublishedNeedListingFactory(title="عنوان مشترک تست")
        assert first.slug != second.slug
        assert second.slug.startswith("عنوان-مشترک-تست")

    def test_category_slug_from_title(self) -> None:
        category = KindnessCategory(title="لوازم آشپزخانه")
        category.full_clean(exclude=["slug"])
        category.save()
        assert category.slug == "لوازم-آشپزخانه"

    def test_search_document_built_from_all_context(self) -> None:
        listing = PublishedNeedListingFactory(
            title="پتو", city="شوش", category=KindnessCategoryFactory(title="پوشاک")
        )
        assert "پتو" in listing.search_document
        assert "شوش" in listing.search_document
        assert "پوشاک" in listing.search_document


class TestVisibilityAndCounters:
    def test_board_queryset_respects_status_and_expiry(self) -> None:
        from datetime import timedelta

        from django.utils import timezone

        live = PublishedNeedListingFactory()
        expired = PublishedNeedListingFactory(expires_at=timezone.now() - timedelta(days=1))
        draft = KindnessListingFactory()
        slugs = {row.slug for row in KindnessListing.objects.published()}
        assert live.slug in slugs
        assert expired.slug not in slugs
        assert draft.slug not in slugs
        assert not expired.is_public

    def test_is_featured_pins_before_published_at(self) -> None:
        """ترتیب پیش‌فرض تخته: ویژه‌ها بالا، سپس تازه‌ترین‌ها."""
        plain = PublishedNeedListingFactory()
        special = PublishedNeedListingFactory(is_featured=True)
        # plain قدیمی‌تر از special است؛ با این حال ویژه باید اول بیاید
        assert not plain.is_featured
        assert special.is_featured
        slugs = [row.slug for row in KindnessListing.objects.published()]
        assert slugs.index(special.slug) < slugs.index(plain.slug)

    def test_days_left_semantics(self) -> None:
        from datetime import timedelta

        from django.utils import timezone

        listing = KindnessListingFactory()
        assert listing.days_left is None
        KindnessListing.all_objects.filter(pk=listing.pk).update(
            expires_at=timezone.now() + timedelta(days=5)
        )
        listing.refresh_from_db()
        assert listing.days_left == 4 or listing.days_left == 5  # لبهٔ کسر روز

    def test_urgency_choices_present(self) -> None:
        assert [value for value, _label in Urgency.choices] == ["normal", "urgent"]
        assert [value for value, _label in ListingStatus.choices] == [
            "draft",
            "published",
            "fulfilled",
            "expired",
            "archived",
        ]
        assert OfferStatus.NEW == "new"

    def test_ttl_default_constant_aligned_with_settings(self) -> None:
        from django.conf import settings

        assert settings.KINDNESS_LISTING_TTL_DAYS == DEFAULT_LISTING_TTL_DAYS


class TestListingImages:
    """کاور خودکار — بدون ستون denormalize و سازگار با MySQL."""

    def _image(self, listing, name: str = "a.png") -> KindnessListingImage:
        file_obj = SimpleUploadedFile(
            name, b"\x89PNG\r\n\x1a\n" + b"0" * 64, content_type="image/png"
        )
        return KindnessListingImage.objects.create(listing=listing, image=file_obj)

    def test_first_image_becomes_cover_automatically(self) -> None:
        listing = PublishedNeedListingFactory()
        first = self._image(listing)
        second = self._image(listing, name="b.png")
        first.refresh_from_db()
        assert first.is_cover is True
        assert second.is_cover is False

    def test_explicit_cover_demotes_others(self) -> None:
        listing = PublishedNeedListingFactory()
        first = self._image(listing)
        second = self._image(listing, name="b.png")
        second.is_cover = True
        second.save(update_fields=["is_cover"])
        first.refresh_from_db()
        second.refresh_from_db()
        assert second.is_cover is True
        assert first.is_cover is False

    def test_cover_deletion_promotes_successor(self) -> None:
        listing = PublishedNeedListingFactory()
        first = self._image(listing)
        second = self._image(listing, name="b.png")
        first.delete()
        second.refresh_from_db()
        assert second.is_cover is True

    def test_upload_path_layout(self) -> None:
        listing = PublishedNeedListingFactory()
        image = KindnessListingImage(listing=listing)
        path = listing_image_upload_path(image, "photo.png")
        assert path == f"kindness_wall/listings/{listing.pk}/images/photo.png"

    def test_max_images_constant_defined(self) -> None:
        from apps.kindness_wall.choices import MAX_IMAGES_PER_LISTING

        assert MAX_IMAGES_PER_LISTING >= 6


class TestOfferUniqueness:
    def test_one_offer_per_user_per_listing_at_db_level(self) -> None:
        from django.db import IntegrityError, transaction

        from tests.factories import UserFactory

        listing = PublishedNeedListingFactory()
        user = UserFactory()
        KindnessOffer.objects.create(listing=listing, user=user)
        with pytest.raises(IntegrityError), transaction.atomic():
            KindnessOffer.objects.create(listing=listing, user=user)
