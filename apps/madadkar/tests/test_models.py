"""
تست‌های پایه مدل‌های اپ مددکار.

پوشش:
- Sponsor: ساخت، slug auto-gen، unique name
- Campaign: ساخت، share_price محاسبه‌ای، slug auto-gen، properties، constraints
- CampaignImage: ساخت، ordering
- Participation: ساخت، snapshot consistency
- Payment: ساخت، authority unique
- BaseModel features: soft delete، active manager
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.madadkar.choices import CampaignStatus, ParticipationStatus, PaymentStatus
from apps.madadkar.models import Campaign, CampaignImage, Sponsor
from tests.factories.madadkar import (
    CampaignFactory,
    CampaignImageFactory,
    CompletedCampaignFactory,
    PaidParticipationFactory,
    ParticipationFactory,
    PaymentFactory,
    PublishedCampaignFactory,
    SponsorFactory,
    SuccessPaymentFactory,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Sponsor tests
# ---------------------------------------------------------------------------


class TestSponsorModel:
    """تست‌های مدل Sponsor."""

    def test_create_sponsor_basic(self):
        """ساخت پایه‌ای Sponsor."""
        sponsor = SponsorFactory(name="بنیاد علوی")

        assert sponsor.pk is not None
        assert sponsor.name == "بنیاد علوی"
        assert sponsor.is_active is True

    def test_sponsor_slug_auto_generated_from_name(self):
        """slug باید به‌صورت خودکار از name ساخته شود."""
        sponsor = SponsorFactory(name="گروه جهادی انصارالزهرا")

        assert sponsor.slug
        assert "انصارالزهرا" in sponsor.slug

    def test_sponsor_name_unique(self):
        """نام مددکار باید unique باشد."""
        SponsorFactory(name="یکتای تستی")

        with pytest.raises(IntegrityError):
            # get_or_create رو غیرفعال می‌کنیم با ساخت دستی
            Sponsor.objects.create(name="یکتای تستی")

    def test_sponsor_str_returns_name(self):
        """__str__ باید نام را برگرداند."""
        sponsor = SponsorFactory(name="تست استرینگ")
        assert str(sponsor) == "تست استرینگ"

    def test_sponsor_soft_delete(self):
        """soft delete باید is_active را False کند."""
        sponsor = SponsorFactory()
        sponsor.soft_delete()

        sponsor.refresh_from_db()
        assert sponsor.is_active is False

    def test_sponsor_active_manager_filters_deleted(self):
        """active manager نباید رکوردهای soft-deleted را برگرداند."""
        active = SponsorFactory()
        deleted = SponsorFactory()
        deleted.soft_delete()

        active_ids = list(Sponsor.objects.values_list("pk", flat=True))
        all_ids = list(Sponsor.all_objects.values_list("pk", flat=True))

        assert active.pk in active_ids
        assert deleted.pk not in active_ids
        assert deleted.pk in all_ids


# ---------------------------------------------------------------------------
# Campaign tests
# ---------------------------------------------------------------------------


class TestCampaignModel:
    """تست‌های مدل Campaign."""

    def test_create_campaign_basic(self):
        """ساخت پایه‌ای Campaign در وضعیت DRAFT."""
        campaign = CampaignFactory()

        assert campaign.pk is not None
        assert campaign.status == CampaignStatus.DRAFT
        assert campaign.is_visible is False
        assert campaign.purchased_shares == 0
        assert campaign.purchased_amount == 0

    def test_share_price_auto_calculated(self):
        """share_price باید از total_amount/total_shares محاسبه شود."""
        campaign = CampaignFactory(
            total_amount=10_000_000_000,
            total_shares=1000,
        )
        assert campaign.share_price == 10_000_000

    def test_share_price_recalculated_on_update(self):
        """تغییر مبلغ کل یا تعداد سهم باید share_price را آپدیت کند."""
        campaign = CampaignFactory(
            total_amount=1_000_000,
            total_shares=100,
        )
        assert campaign.share_price == 10_000

        campaign.total_amount = 2_000_000
        campaign.save()
        assert campaign.share_price == 20_000

    def test_campaign_slug_auto_generated(self):
        """slug باید از title ساخته شود."""
        campaign = CampaignFactory(title="خرید پشه‌بند برای جبهه")
        assert campaign.slug
        assert "پشه" in campaign.slug or "جبهه" in campaign.slug

    def test_campaign_str_returns_title(self):
        """__str__ باید title را برگرداند."""
        campaign = CampaignFactory(title="عنوان تست")
        assert str(campaign) == "عنوان تست"

    # ── Properties ────────────────────────────────────────────────────

    def test_remaining_shares_property(self):
        """remaining_shares = total_shares - purchased_shares."""
        campaign = CampaignFactory(total_shares=1000)
        campaign.purchased_shares = 300
        assert campaign.remaining_shares == 700

    def test_remaining_shares_never_negative(self):
        """در شرایط غیرمنتظره (که نباید رخ دهد)، remaining_shares منفی نشود."""
        campaign = CampaignFactory(total_shares=1000)
        campaign.purchased_shares = 1500  # ولی DB constraint جلوگیری می‌کند
        assert campaign.remaining_shares == 0

    def test_progress_percent_property(self):
        """progress_percent با یک رقم اعشار محاسبه شود."""
        campaign = CampaignFactory(total_shares=1000)
        campaign.purchased_shares = 250
        assert campaign.progress_percent == 25.0

        campaign.purchased_shares = 333
        assert campaign.progress_percent == 33.3

    def test_progress_percent_zero_total_shares(self):
        """در صورت 0 بودن total_shares (impossible due to constraint)، 0 برگردد."""
        # نمی‌توان با factory ساخت — مستقیماً property را تست می‌کنیم
        campaign = CampaignFactory()
        campaign.total_shares = 0
        assert campaign.progress_percent == 0.0

    def test_is_fully_funded_property(self):
        """is_fully_funded زمانی True که سهم‌ها پر شوند."""
        campaign = CampaignFactory(total_shares=1000)
        assert campaign.is_fully_funded is False

        campaign.purchased_shares = 1000
        assert campaign.is_fully_funded is True

    # ── Constraints ───────────────────────────────────────────────────

    def test_constraint_total_amount_min(self):
        """total_amount نمی‌تواند کمتر از ۱۰۰۰ تومان باشد."""
        sponsor = SponsorFactory()
        with pytest.raises(IntegrityError):
            Campaign.objects.create(
                sponsor=sponsor,
                title="کم‌مبلغ",
                description="...",
                cover_image="dummy.png",
                total_amount=500,
                total_shares=1,
                share_price=500,
            )

    def test_constraint_purchased_lte_total(self):
        """purchased_shares نمی‌تواند بیش از total_shares باشد."""
        campaign = CampaignFactory(total_shares=100)
        campaign.purchased_shares = 101

        with pytest.raises(IntegrityError):
            campaign.save()

    def test_constraint_deadline_consistency_has_deadline_true_requires_date(self):
        """اگر has_deadline=True باشد، deadline نباید null باشد."""
        sponsor = SponsorFactory()
        with pytest.raises(IntegrityError):
            Campaign.objects.create(
                sponsor=sponsor,
                title="بی‌مهلت متناقض",
                description="...",
                cover_image="dummy.png",
                total_amount=1_000_000,
                total_shares=100,
                share_price=10_000,
                has_deadline=True,
                deadline=None,
            )

    def test_constraint_deadline_consistency_no_deadline_requires_null(self):
        """اگر has_deadline=False باشد، deadline باید null باشد."""
        sponsor = SponsorFactory()
        with pytest.raises(IntegrityError):
            Campaign.objects.create(
                sponsor=sponsor,
                title="بی‌مهلت با تاریخ",
                description="...",
                cover_image="dummy.png",
                total_amount=1_000_000,
                total_shares=100,
                share_price=10_000,
                has_deadline=False,
                deadline=timezone.now() + timezone.timedelta(days=30),
            )


# ---------------------------------------------------------------------------
# Campaign Managers tests
# ---------------------------------------------------------------------------


class TestCampaignManagers:
    """تست‌های manager‌های Campaign (visible, accepting)."""

    def test_visible_manager_excludes_draft(self):
        """visible manager نباید حرکت‌های DRAFT را برگرداند."""
        draft = CampaignFactory()  # DRAFT default
        published = PublishedCampaignFactory()

        visible_ids = list(Campaign.visible.values_list("pk", flat=True))
        assert draft.pk not in visible_ids
        assert published.pk in visible_ids

    def test_visible_manager_excludes_invisible(self):
        """visible manager نباید حرکت‌های is_visible=False را برگرداند."""
        invisible = PublishedCampaignFactory(is_visible=False)
        visible = PublishedCampaignFactory(is_visible=True)

        ids = list(Campaign.visible.values_list("pk", flat=True))
        assert invisible.pk not in ids
        assert visible.pk in ids

    def test_visible_manager_includes_completed_and_closed(self):
        """visible manager باید COMPLETED و CLOSED را هم برگرداند."""
        completed = CompletedCampaignFactory()

        ids = list(Campaign.visible.values_list("pk", flat=True))
        assert completed.pk in ids

    def test_accepting_manager_only_published(self):
        """accepting manager فقط PUBLISHED را برگرداند."""
        published = PublishedCampaignFactory()
        completed = CompletedCampaignFactory()

        ids = list(Campaign.accepting.values_list("pk", flat=True))
        assert published.pk in ids
        assert completed.pk not in ids


# ---------------------------------------------------------------------------
# CampaignImage tests
# ---------------------------------------------------------------------------


class TestCampaignImageModel:
    """تست‌های مدل CampaignImage."""

    def test_create_gallery_image(self):
        """ساخت پایه‌ای تصویر گالری."""
        image = CampaignImageFactory()

        assert image.pk is not None
        assert image.campaign is not None
        assert image.image is not None

    def test_gallery_images_ordering(self):
        """تصاویر بر اساس display_order مرتب شوند."""
        campaign = PublishedCampaignFactory()
        img2 = CampaignImageFactory(campaign=campaign, display_order=2)
        img1 = CampaignImageFactory(campaign=campaign, display_order=1)
        img3 = CampaignImageFactory(campaign=campaign, display_order=3)

        images = list(CampaignImage.objects.filter(campaign=campaign))
        assert images == [img1, img2, img3]

    def test_campaign_cascade_deletes_gallery(self):
        """با حذف Campaign، گالری هم حذف شود."""
        campaign = PublishedCampaignFactory()
        CampaignImageFactory(campaign=campaign)
        CampaignImageFactory(campaign=campaign)

        campaign_pk = campaign.pk
        assert CampaignImage.objects.filter(campaign_id=campaign_pk).count() == 2

        campaign.delete()
        assert CampaignImage.objects.filter(campaign_id=campaign_pk).count() == 0


# ---------------------------------------------------------------------------
# Participation tests
# ---------------------------------------------------------------------------


class TestParticipationModel:
    """تست‌های مدل Participation."""

    def test_create_participation_basic(self):
        """ساخت پایه‌ای Participation."""
        p = ParticipationFactory(share_count=5)

        assert p.pk is not None
        assert p.share_count == 5
        assert p.status == ParticipationStatus.PENDING_PAYMENT

    def test_share_price_snapshot_matches_campaign_at_creation(self):
        """snapshot باید با قیمت لحظه ساخت برابر باشد."""
        campaign = PublishedCampaignFactory(
            total_amount=5_000_000_000,
            total_shares=500,
        )
        # قیمت فعلی هر سهم = 10,000,000
        p = ParticipationFactory(campaign=campaign, share_count=3)

        assert p.share_price_snapshot == 10_000_000
        assert p.total_amount == 30_000_000

    def test_snapshot_immutable_after_campaign_price_change(self):
        """تغییر قیمت بعد از ساخت Participation، snapshot را تغییر ندهد."""
        campaign = PublishedCampaignFactory(
            total_amount=1_000_000,
            total_shares=100,
        )
        p = ParticipationFactory(campaign=campaign, share_count=2)
        original_snapshot = p.share_price_snapshot
        original_total = p.total_amount

        # تغییر قیمت سهم (که بعد از اولین پرداخت ممنوع است، ولی برای تست منطق snapshot)
        campaign.total_amount = 2_000_000
        campaign.save()
        p.refresh_from_db()

        # snapshot نباید عوض شود
        assert p.share_price_snapshot == original_snapshot
        assert p.total_amount == original_total

    def test_participation_str(self):
        """__str__ شامل اطلاعات اصلی باشد."""
        p = ParticipationFactory(share_count=7)
        s = str(p)
        assert "Participation" in s
        assert "shares=7" in s


# ---------------------------------------------------------------------------
# Payment tests
# ---------------------------------------------------------------------------


class TestPaymentModel:
    """تست‌های مدل Payment."""

    def test_create_payment_basic(self):
        """ساخت پایه‌ای Payment."""
        payment = PaymentFactory()

        assert payment.pk is not None
        assert payment.status == PaymentStatus.PENDING
        assert payment.gateway_name == "sandbox"
        assert payment.authority.startswith("AUTH-TEST-")

    def test_payment_amount_matches_participation(self):
        """amount باید با total_amount مشارکت برابر باشد."""
        participation = ParticipationFactory(share_count=4)
        payment = PaymentFactory(participation=participation)

        assert payment.amount == participation.total_amount

    def test_payment_user_denormalized_from_participation(self):
        """user باید برابر participation.user باشد."""
        participation = ParticipationFactory()
        payment = PaymentFactory(participation=participation)

        assert payment.user_id == participation.user_id

    def test_payment_authority_unique(self):
        """authority باید unique باشد."""
        PaymentFactory(authority="UNIQUE-001")

        with pytest.raises(IntegrityError):
            PaymentFactory(authority="UNIQUE-001")

    def test_payment_one_to_one_with_participation(self):
        """هر Participation فقط می‌تواند یک Payment داشته باشد."""
        participation = ParticipationFactory()
        PaymentFactory(participation=participation)

        with pytest.raises(IntegrityError):
            PaymentFactory(participation=participation)

    def test_success_payment_factory(self):
        """SuccessPaymentFactory فیلدهای success را پر کند."""
        payment = SuccessPaymentFactory()

        assert payment.status == PaymentStatus.SUCCESS
        assert payment.ref_id
        assert payment.paid_at is not None
        assert payment.verified_at is not None
        assert payment.participation.status == ParticipationStatus.PAID

    def test_payment_str(self):
        """__str__ شامل authority و status باشد."""
        payment = PaymentFactory(authority="AUTH-XYZ-123")
        s = str(payment)
        assert "AUTH-XYZ-123" in s
        assert "pending" in s

    def test_paid_participation_factory_has_paid_at(self):
        """PaidParticipationFactory باید paid_at داشته باشد."""
        p = PaidParticipationFactory()
        assert p.status == ParticipationStatus.PAID
        assert p.paid_at is not None


class TestCampaignSlugGeneration:
    """Campaign slug generation should be admin-friendly and collision-safe."""

    def test_duplicate_titles_generate_unique_slugs(self) -> None:
        first = CampaignFactory(title="تست")
        second = CampaignFactory(title="تست")

        assert first.slug == "تست"
        assert second.slug.startswith("تست-")
        assert second.slug != first.slug
