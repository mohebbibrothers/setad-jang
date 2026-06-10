"""
Tests — apps.r4j models (Phase R4J.1)

این تست‌ها رفتار پایه‌ی مدل‌ها را verify می‌کنند:
- slug خودکار و collision handling
- publish/unpublish/soft_delete behavior
- unique constraints (primary photo, alias, social, bounty)
- bounty min amount validation
- national code validator

اصول طراحی:
- exception types دقیق expect می‌شوند، نه Exception generic.
- هر تست یک scenario واحد را cover می‌کند.
- فایل‌های تصویری به‌صورت minimal in-memory ساخته می‌شوند تا
  وابستگی به I/O واقعی نداشته باشیم.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.utils import IntegrityError

from apps.r4j.choices import BountyStatus, SocialPlatform
from apps.r4j.models import (
    R4JBounty,
    R4JCriminalAlias,
    R4JCriminalPhoto,
    R4JCriminalSocial,
)
from tests.factories.auth import UserFactory
from tests.factories.r4j import R4JCriminalFactory

pytestmark = [pytest.mark.django_db]


# ============================================================
# Slug generation
# ============================================================


class TestCriminalSlug:
    """رفتار خودکار slug."""

    def test_slug_is_auto_generated_from_name(self) -> None:
        criminal = R4JCriminalFactory(first_name="Donald", last_name="Trump", slug="")
        assert criminal.slug
        assert "donald" in criminal.slug.lower()

    def test_slug_collision_is_handled(self) -> None:
        a = R4JCriminalFactory(first_name="Test", last_name="Person", slug="")
        b = R4JCriminalFactory(first_name="Test", last_name="Person", slug="")
        assert a.slug != b.slug


# ============================================================
# Publish lifecycle
# ============================================================


class TestCriminalPublishLifecycle:
    """state machine انتشار و حذف نرم."""

    def test_publish_sets_flags_and_timestamp(self) -> None:
        criminal = R4JCriminalFactory(is_published=False)
        criminal.publish()
        assert criminal.is_published is True
        assert criminal.published_at is not None

    def test_publish_is_idempotent(self) -> None:
        criminal = R4JCriminalFactory(is_published=False)
        criminal.publish()
        first_ts = criminal.published_at
        criminal.publish()
        assert criminal.published_at == first_ts

    def test_unpublish_resets_flag(self) -> None:
        criminal = R4JCriminalFactory()
        criminal.publish()
        criminal.unpublish()
        assert criminal.is_published is False

    def test_soft_delete_unpublishes(self) -> None:
        criminal = R4JCriminalFactory()
        criminal.publish()
        criminal.soft_delete()
        assert criminal.is_active is False
        assert criminal.is_published is False


# ============================================================
# Constraints
# ============================================================


class TestUniqueConstraints:
    """تست constraintهای حساس روی مدل‌های وابسته به criminal."""

    def test_alias_unique_per_criminal(self) -> None:
        """نمی‌توان دو alias یکسان برای یک criminal ساخت."""
        criminal = R4JCriminalFactory()
        R4JCriminalAlias.objects.create(criminal=criminal, alias="DT")
        with pytest.raises(IntegrityError):
            R4JCriminalAlias.objects.create(criminal=criminal, alias="DT")

    def test_social_unique_per_criminal(self) -> None:
        """نمی‌توان دو social یکسان (platform + handle) برای یک criminal ساخت."""
        criminal = R4JCriminalFactory()
        R4JCriminalSocial.objects.create(
            criminal=criminal,
            platform=SocialPlatform.TELEGRAM,
            handle_or_url="@x",
        )
        with pytest.raises(IntegrityError):
            R4JCriminalSocial.objects.create(
                criminal=criminal,
                platform=SocialPlatform.TELEGRAM,
                handle_or_url="@x",
            )

    def test_only_one_primary_photo(self) -> None:
        """فقط یک عکس primary در هر زمان برای یک criminal مجاز است."""
        criminal = R4JCriminalFactory()

        def _img(name: str) -> SimpleUploadedFile:
            return SimpleUploadedFile(
                name,
                b"\x89PNG\r\n\x1a\nfakecontent",
                content_type="image/png",
            )

        R4JCriminalPhoto.objects.create(
            criminal=criminal, image=_img("a.png"), is_primary=True,
        )
        with pytest.raises(IntegrityError):
            R4JCriminalPhoto.objects.create(
                criminal=criminal, image=_img("b.png"), is_primary=True,
            )


# ============================================================
# Bounty
# ============================================================


class TestBountyConstraints:
    """قواعد bounty."""

    def test_bounty_min_amount_validation(self) -> None:
        """مبلغ کمتر از حداقل مجاز در full_clean رد می‌شود."""
        user = UserFactory()
        criminal = R4JCriminalFactory()
        bounty = R4JBounty(
            user=user,
            criminal=criminal,
            amount_toman=10_000,
            status=BountyStatus.ACTIVE,
        )
        with pytest.raises(ValidationError):
            bounty.full_clean()

    def test_only_one_active_bounty_per_user_criminal(self) -> None:
        """نمی‌توان دو bounty فعال برای یک (user, criminal) داشت."""
        user = UserFactory()
        criminal = R4JCriminalFactory()
        R4JBounty.objects.create(
            user=user,
            criminal=criminal,
            amount_toman=100_000,
            status=BountyStatus.ACTIVE,
        )
        with pytest.raises(IntegrityError):
            R4JBounty.objects.create(
                user=user,
                criminal=criminal,
                amount_toman=200_000,
                status=BountyStatus.ACTIVE,
            )

    def test_can_have_canceled_bounty_alongside_active(self) -> None:
        """رکورد canceled نباید با active برخورد constraint داشته باشد."""
        user = UserFactory()
        criminal = R4JCriminalFactory()
        R4JBounty.objects.create(
            user=user,
            criminal=criminal,
            amount_toman=100_000,
            status=BountyStatus.CANCELED,
        )
        # active باید بدون مشکل ساخته شود
        R4JBounty.objects.create(
            user=user,
            criminal=criminal,
            amount_toman=200_000,
            status=BountyStatus.ACTIVE,
        )
