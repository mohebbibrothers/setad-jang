"""Factories for Kindness Wall tests."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from apps.authentication.choices import Gender
from apps.kindness_wall.choices import ListingStatus, ListingType
from apps.kindness_wall.models import KindnessCategory, KindnessListing, KindnessTag
from tests.factories.auth import UserFactory


class KindnessCategoryFactory(DjangoModelFactory):
    """Factory for Kindness Wall tree categories."""

    class Meta:
        model = KindnessCategory

    title = factory.Sequence(lambda n: f"دسته مهربانی {n}")
    description = "توضیحات دسته"
    order = factory.Sequence(lambda n: n)


class KindnessUserFactory(UserFactory):
    """Factory for users eligible to create listings."""

    first_name = "علی"
    last_name = "محمدی"
    phone_number = factory.Sequence(lambda n: f"+98912000{n:04d}")
    is_phone_verified = True

    @factory.post_generation
    def complete_profile(obj, create: bool, extracted, **kwargs) -> None:
        """Complete profile fields required by Kindness Wall."""
        if not create:
            return
        obj.profile.national_code = "0123456789"
        obj.profile.gender = Gender.MALE
        obj.profile.province = "تهران"
        obj.profile.city = "تهران"
        obj.profile.save(update_fields=["national_code", "gender", "province", "city"])


class KindnessListingFactory(DjangoModelFactory):
    """Factory for Kindness Wall listings."""

    class Meta:
        model = KindnessListing

    owner = factory.SubFactory(KindnessUserFactory)
    listing_type = ListingType.NEED_HELP
    category = factory.SubFactory(KindnessCategoryFactory)
    title = factory.Sequence(lambda n: f"آگهی مهربانی {n}")
    description = "توضیح کامل آگهی برای کمک‌رسانی و ارتباط انسانی"
    province = "تهران"
    city = "تهران"
    contact_phone_snapshot = factory.SelfAttribute("owner.phone_number")
    owner_full_name_snapshot = "علی محمدی"
    owner_gender_snapshot = Gender.MALE
    owner_province_snapshot = "تهران"
    owner_city_snapshot = "تهران"
    status = ListingStatus.DRAFT


class PublishedNeedListingFactory(KindnessListingFactory):
    """Published need-help listing."""

    listing_type = ListingType.NEED_HELP
    status = ListingStatus.PUBLISHED


class PublishedOfferListingFactory(KindnessListingFactory):
    """Published offer-help listing."""

    listing_type = ListingType.OFFER_HELP
    status = ListingStatus.PUBLISHED


class KindnessTagFactory(DjangoModelFactory):
    """Factory for global tags."""

    class Meta:
        model = KindnessTag

    name = factory.Sequence(lambda n: f"tag-{n}")
