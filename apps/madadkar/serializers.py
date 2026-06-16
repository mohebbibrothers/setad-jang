"""
Serializers اپ مددکار.

ساختار:
- Sponsor serializers: Public, Admin (CRUD), Detail
- Campaign serializers: Public List, Public Detail, Admin List, Admin Detail,
  Admin Create, Admin Update, Publish/Close actions
- CampaignImage serializers: Read, Create, Update
- Participation serializers: Initiate (input), User Read (list/detail)
- Payment serializers: User Read (detail با redirect_url)
- Payment Verify Callback serializer
- Admin Analytics serializers: Participant, Leaderboard, Analytics
- Admin Payment serializers: List (همه پرداخت‌ها برای ادمین)

اصول طراحی:
- تفکیک واضح بین input و output serializers.
- read_only فیلدهای محاسبه‌شده (مثل share_price, progress_percent).
- استفاده از Method fields برای properties مدل.
- validation سبک — منطق سنگین در service layer انجام می‌شود.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.madadkar.choices import (
    CampaignStatus,
    FinancialAdjustmentType,
    MadadkarRiskSeverity,
    MadadkarRiskStatus,
    RefundReason,
)
from apps.madadkar.models import (
    Campaign,
    CampaignDisbursement,
    CampaignFinancialAdjustment,
    CampaignImage,
    DonationReceipt,
    MadadkarRiskSignal,
    Participation,
    Payment,
    PaymentReconciliationBatch,
    PaymentReconciliationItem,
    PaymentRefund,
    Sponsor,
)
from apps.madadkar.validators import (
    validate_image_extension,
    validate_image_size,
    validate_share_count,
    validate_total_amount,
    validate_total_shares,
)

# ===========================================================================
# Sponsor serializers
# ===========================================================================

class SponsorPublicSerializer(serializers.ModelSerializer):
    """نمایش عمومی مددکار — فقط فیلدهای امن."""

    class Meta:
        model = Sponsor
        fields = ("id", "name", "slug", "logo")
        read_only_fields = fields


class SponsorAdminSerializer(serializers.ModelSerializer):
    """نمایش کامل مددکار برای ادمین."""

    campaigns_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Sponsor
        fields = (
            "id",
            "name",
            "slug",
            "logo",
            "is_active",
            "campaigns_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "slug",
            "is_active",
            "campaigns_count",
            "created_at",
            "updated_at",
        )

    def get_campaigns_count(self, obj: Sponsor) -> int:
        """تعداد حرکت‌های فعال این مددکار."""
        return obj.campaigns.filter(is_active=True).count()


class SponsorCreateSerializer(serializers.Serializer):
    """ورودی ساخت Sponsor توسط ادمین."""

    name = serializers.CharField(max_length=200)
    logo = serializers.ImageField(
        required=False,
        allow_null=True,
        validators=[validate_image_extension, validate_image_size],
    )


class SponsorUpdateSerializer(serializers.Serializer):
    """ورودی ویرایش Sponsor توسط ادمین — تمام فیلدها اختیاری."""

    name = serializers.CharField(max_length=200, required=False)
    logo = serializers.ImageField(
        required=False,
        allow_null=True,
        validators=[validate_image_extension, validate_image_size],
    )


# ===========================================================================
# CampaignImage serializers
# ===========================================================================

class CampaignImageReadSerializer(serializers.ModelSerializer):
    """نمایش تصویر گالری."""

    class Meta:
        model = CampaignImage
        fields = (
            "id",
            "image",
            "alt_text",
            "display_order",
            "created_at",
        )
        read_only_fields = fields


class CampaignImageCreateSerializer(serializers.Serializer):
    """ورودی افزودن تصویر به گالری."""

    image = serializers.ImageField(
        validators=[validate_image_extension, validate_image_size],
    )
    alt_text = serializers.CharField(
        max_length=200,
        required=False,
        allow_blank=True,
        default="",
    )
    display_order = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=0,
    )


# ===========================================================================
# Campaign serializers — public
# ===========================================================================

class CampaignPublicListSerializer(serializers.ModelSerializer):
    """نمایش حرکت در لیست عمومی — سبک‌وزن."""

    sponsor = SponsorPublicSerializer(read_only=True)
    remaining_shares = serializers.IntegerField(read_only=True)
    progress_percent = serializers.FloatField(read_only=True)
    is_fully_funded = serializers.BooleanField(read_only=True)
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = Campaign
        fields = (
            "id",
            "sponsor",
            "title",
            "slug",
            "cover_image",
            "total_amount",
            "total_shares",
            "share_price",
            "purchased_shares",
            "purchased_amount",
            "participant_count",
            "remaining_shares",
            "progress_percent",
            "is_fully_funded",
            "status",
            "status_display",
            "has_deadline",
            "deadline",
            "published_at",
            "completed_at",
            "closed_at",
        )
        read_only_fields = fields


class CampaignPublicDetailSerializer(CampaignPublicListSerializer):
    """نمایش جزئیات حرکت در صفحه detail عمومی — همراه گالری و توضیحات کامل."""

    description = serializers.CharField(read_only=True)
    gallery_images = CampaignImageReadSerializer(
        many=True,
        read_only=True,
    )

    class Meta(CampaignPublicListSerializer.Meta):
        fields = (
            *CampaignPublicListSerializer.Meta.fields,
            "description",
            "gallery_images",
        )
        read_only_fields = fields


# ===========================================================================
# Campaign serializers — admin
# ===========================================================================

class CampaignAdminListSerializer(serializers.ModelSerializer):
    """لیست حرکت‌ها برای ادمین — همه فیلدهای کلیدی."""

    sponsor = SponsorPublicSerializer(read_only=True)
    remaining_shares = serializers.IntegerField(read_only=True)
    progress_percent = serializers.FloatField(read_only=True)
    is_fully_funded = serializers.BooleanField(read_only=True)
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = Campaign
        fields = (
            "id",
            "sponsor",
            "title",
            "slug",
            "cover_image",
            "total_amount",
            "total_shares",
            "share_price",
            "purchased_shares",
            "purchased_amount",
            "participant_count",
            "remaining_shares",
            "progress_percent",
            "is_fully_funded",
            "status",
            "status_display",
            "is_visible",
            "is_active",
            "has_deadline",
            "deadline",
            "published_at",
            "completed_at",
            "closed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class CampaignAdminDetailSerializer(CampaignAdminListSerializer):
    """جزئیات کامل حرکت برای ادمین — همراه گالری و توضیحات."""

    description = serializers.CharField(read_only=True)
    gallery_images = CampaignImageReadSerializer(many=True, read_only=True)

    class Meta(CampaignAdminListSerializer.Meta):
        fields = (
            *CampaignAdminListSerializer.Meta.fields,
            "description",
            "gallery_images",
        )
        read_only_fields = fields


class CampaignAdminCreateSerializer(serializers.Serializer):
    """ورودی ساخت Campaign توسط ادمین."""

    sponsor_id = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=300)
    description = serializers.CharField()
    cover_image = serializers.ImageField(
        validators=[validate_image_extension, validate_image_size],
    )
    total_amount = serializers.IntegerField(
        min_value=1000,
        validators=[validate_total_amount],
    )
    total_shares = serializers.IntegerField(
        min_value=1,
        validators=[validate_total_shares],
    )
    has_deadline = serializers.BooleanField(default=False)
    deadline = serializers.DateTimeField(
        required=False,
        allow_null=True,
        default=None,
    )
    is_visible = serializers.BooleanField(default=False)

    def validate(self, attrs: dict) -> dict:
        """اعتبارسنجی cross-field در سطح serializer."""
        has_deadline = attrs.get("has_deadline", False)
        deadline = attrs.get("deadline")

        if has_deadline and deadline is None:
            raise serializers.ValidationError({
                "deadline": "در صورت فعال بودن مهلت زمانی، تاریخ پایان الزامی است.",
            })
        if not has_deadline and deadline is not None:
            raise serializers.ValidationError({
                "deadline": "اگر مهلت زمانی فعال نیست، تاریخ پایان نباید مقداردهی شود.",
            })

        total_amount = attrs["total_amount"]
        total_shares = attrs["total_shares"]
        if total_amount % total_shares != 0:
            raise serializers.ValidationError({
                "total_amount": (
                    f"مبلغ کل ({total_amount:,}) باید بر تعداد سهم "
                    f"({total_shares:,}) بدون باقیمانده تقسیم شود."
                ),
            })

        return attrs


class CampaignAdminUpdateSerializer(serializers.Serializer):
    """ورودی ویرایش Campaign توسط ادمین."""

    sponsor_id = serializers.IntegerField(required=False, min_value=1)
    title = serializers.CharField(max_length=300, required=False)
    description = serializers.CharField(required=False)
    cover_image = serializers.ImageField(
        required=False,
        validators=[validate_image_extension, validate_image_size],
    )
    total_amount = serializers.IntegerField(
        required=False,
        min_value=1000,
        validators=[validate_total_amount],
    )
    total_shares = serializers.IntegerField(
        required=False,
        min_value=1,
        validators=[validate_total_shares],
    )
    has_deadline = serializers.BooleanField(required=False)
    deadline = serializers.DateTimeField(
        required=False,
        allow_null=True,
    )
    is_visible = serializers.BooleanField(required=False)

    def validate(self, attrs: dict) -> dict:
        """اعتبارسنجی تقسیم‌پذیری در صورت تغییر فیلدهای مالی."""
        if "total_amount" in attrs or "total_shares" in attrs:
            campaign = self.context.get("campaign")
            new_amount = attrs.get(
                "total_amount",
                campaign.total_amount if campaign else None,
            )
            new_shares = attrs.get(
                "total_shares",
                campaign.total_shares if campaign else None,
            )
            if (
                new_amount is not None
                and new_shares is not None
                and new_amount % new_shares != 0
            ):
                raise serializers.ValidationError({
                    "total_amount": (
                        f"مبلغ کل ({new_amount:,}) باید بر تعداد سهم "
                        f"({new_shares:,}) بدون باقیمانده تقسیم شود."
                    ),
                })

        return attrs


# ===========================================================================
# Status display helper
# ===========================================================================

class CampaignStatusChoiceSerializer(serializers.Serializer):
    """نمایش choiceهای CampaignStatus برای کمک به UI."""

    value = serializers.CharField()
    label = serializers.CharField()

    @classmethod
    def get_all_choices(cls) -> list[dict[str, str]]:
        """لیست تمام choiceها برای استفاده در API kit."""
        return [
            {"value": value, "label": label}
            for value, label in CampaignStatus.choices
        ]


# ===========================================================================
# Participation serializers
# ===========================================================================

class ParticipationInitiateSerializer(serializers.Serializer):
    """
    ورودی شروع مشارکت توسط کاربر.

    کاربر یک share_count می‌دهد (تعداد سهم درخواستی).
    قیمت سهم و مبلغ کل از Campaign استخراج می‌شود (snapshot در service).

    نکات اختیاری:
    - mobile/email: برخی درگاه‌ها از این‌ها استفاده می‌کنند.
      اگر ارسال نشوند، از پروفایل کاربر استخراج می‌شوند.
    """

    share_count = serializers.IntegerField(
        min_value=1,
        validators=[validate_share_count],
        help_text="تعداد سهمی که می‌خواهید خریداری کنید (حداقل ۱).",
    )
    mobile = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        default="",
        help_text="شماره موبایل برای ارسال به درگاه (اختیاری).",
    )
    email = serializers.EmailField(
        required=False,
        allow_blank=True,
        default="",
        help_text="ایمیل برای ارسال به درگاه (اختیاری).",
    )


class ParticipationCampaignSummarySerializer(serializers.ModelSerializer):
    """خلاصه‌ای از Campaign برای نمایش در داخل Participation."""

    sponsor = SponsorPublicSerializer(read_only=True)
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = Campaign
        fields = (
            "id",
            "title",
            "slug",
            "cover_image",
            "sponsor",
            "status",
            "status_display",
        )
        read_only_fields = fields


class ParticipationUserListSerializer(serializers.ModelSerializer):
    """لیست مشارکت‌های کاربر — سبک‌وزن."""

    campaign = ParticipationCampaignSummarySerializer(read_only=True)
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = Participation
        fields = (
            "id",
            "campaign",
            "share_count",
            "share_price_snapshot",
            "total_amount",
            "status",
            "status_display",
            "created_at",
            "paid_at",
        )
        read_only_fields = fields


class PaymentUserSummarySerializer(serializers.ModelSerializer):
    """خلاصه پرداخت برای نمایش در داخل Participation detail."""

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = Payment
        fields = (
            "id",
            "gateway_name",
            "authority",
            "ref_id",
            "amount",
            "status",
            "status_display",
            "paid_at",
            "verified_at",
        )
        read_only_fields = fields


class ParticipationUserDetailSerializer(ParticipationUserListSerializer):
    """جزئیات مشارکت کاربر — همراه پرداخت."""

    payment = PaymentUserSummarySerializer(read_only=True)

    class Meta(ParticipationUserListSerializer.Meta):
        fields = (
            *ParticipationUserListSerializer.Meta.fields,
            "payment",
        )
        read_only_fields = fields


class ParticipationInitiatedResponseSerializer(serializers.Serializer):
    """
    پاسخ موفقیت‌آمیز شروع مشارکت.

    شامل اطلاعات Participation و URL مقصد درگاه.
    کاربر باید به gateway_url ریدایرکت شود.
    """

    participation = ParticipationUserDetailSerializer(read_only=True)
    gateway_url = serializers.URLField(
        read_only=True,
        help_text="URL کامل درگاه پرداخت — کاربر باید به این URL ریدایرکت شود.",
    )
    authority = serializers.CharField(
        read_only=True,
        help_text="کد رهگیری پرداخت — برای پیگیری و تأیید.",
    )


# ===========================================================================
# Payment Verify Callback serializer
# ===========================================================================

class PaymentVerifyCallbackSerializer(serializers.Serializer):
    """
    ورودی callback تأیید پرداخت از سمت درگاه.

    اکثر درگاه‌ها (Zarinpal, IDPay) با query params برمی‌گردانند:
    - Authority: کد رهگیری
    - Status: وضعیت اولیه (OK / NOK)

    ما این فیلدها را به‌صورت اختیاری دریافت می‌کنیم و در service
    با provider verify می‌کنیم (status اولیه قابل اعتماد نیست).
    """

    authority = serializers.CharField(
        max_length=100,
        help_text="کد رهگیری پرداخت برگشتی از درگاه.",
    )
    status = serializers.CharField(
        max_length=10,
        required=False,
        allow_blank=True,
        default="",
        help_text="وضعیت اولیه از سمت درگاه (OK/NOK) — قابل اعتماد نیست.",
    )


class PaymentVerifyResultSerializer(serializers.Serializer):
    """پاسخ نتیجه verify — برای نمایش به کاربر."""

    payment_status = serializers.CharField(read_only=True)
    payment_status_display = serializers.CharField(read_only=True)
    participation = ParticipationUserDetailSerializer(read_only=True)
    is_verified = serializers.BooleanField(
        read_only=True,
        help_text="آیا پرداخت نهایی موفق بود؟",
    )
    message = serializers.CharField(read_only=True)


# ===========================================================================
# Admin Analytics serializers
# ===========================================================================

class AdminUserSummarySerializer(serializers.Serializer):
    """خلاصه‌ای از User برای نمایش در analytics ادمین."""

    id = serializers.IntegerField(read_only=True)
    email = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    mobile = serializers.SerializerMethodField()

    def get_email(self, obj) -> str:
        return getattr(obj, "email", "") or ""

    def get_display_name(self, obj) -> str:
        full_name = ""
        if hasattr(obj, "get_full_name"):
            full_name = (obj.get_full_name() or "").strip()
        if full_name:
            return full_name
        return getattr(obj, "email", "") or "—"

    def get_mobile(self, obj) -> str:
        return (
            getattr(obj, "phone_number", "")
            or getattr(obj, "mobile", "")
            or ""
        )


class AdminParticipantDetailSerializer(serializers.ModelSerializer):
    """
    جزئیات مشارکت‌کننده برای نمایش در لیست admin participants.

    شامل اطلاعات کاربر، Payment و timing.
    """

    user = AdminUserSummarySerializer(read_only=True)
    payment = PaymentUserSummarySerializer(read_only=True)
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = Participation
        fields = (
            "id",
            "user",
            "share_count",
            "share_price_snapshot",
            "total_amount",
            "status",
            "status_display",
            "payment",
            "created_at",
            "paid_at",
        )
        read_only_fields = fields


class AdminLeaderboardEntrySerializer(serializers.Serializer):
    """یک ردیف از leaderboard — top contributors یک حرکت."""

    user_id = serializers.IntegerField(read_only=True)
    user_email = serializers.CharField(read_only=True)
    user_display_name = serializers.CharField(read_only=True)
    total_shares = serializers.IntegerField(read_only=True)
    total_amount = serializers.IntegerField(read_only=True)
    participations_count = serializers.IntegerField(read_only=True)


class AdminCampaignAnalyticsSerializer(serializers.Serializer):
    """آمار تجمیعی یک حرکت برای دشبورد ادمین."""

    total_participations = serializers.IntegerField(read_only=True)
    paid_participations = serializers.IntegerField(read_only=True)
    pending_participations = serializers.IntegerField(read_only=True)
    failed_participations = serializers.IntegerField(read_only=True)
    expired_participations = serializers.IntegerField(read_only=True)
    total_paid_amount = serializers.IntegerField(read_only=True)
    total_paid_shares = serializers.IntegerField(read_only=True)
    unique_paid_users = serializers.IntegerField(read_only=True)
    progress_percent = serializers.FloatField(read_only=True)
    remaining_shares = serializers.IntegerField(read_only=True)


# ===========================================================================
# Admin Payment serializers (همه پرداخت‌ها — برای ادمین)
# ===========================================================================

class AdminPaymentCampaignSummarySerializer(serializers.ModelSerializer):
    """خلاصه‌ای از Campaign برای نمایش در داخل Payment ادمین."""

    sponsor_name = serializers.CharField(source="sponsor.name", read_only=True)

    class Meta:
        model = Campaign
        fields = ("id", "title", "slug", "sponsor_name")
        read_only_fields = fields


class AdminPaymentListSerializer(serializers.ModelSerializer):
    """لیست پرداخت‌ها برای ادمین — همراه کاربر و حرکت."""

    user = AdminUserSummarySerializer(read_only=True)
    campaign = AdminPaymentCampaignSummarySerializer(
        source="participation.campaign",
        read_only=True,
    )
    share_count = serializers.IntegerField(
        source="participation.share_count",
        read_only=True,
    )
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = Payment
        fields = (
            "id",
            "user",
            "campaign",
            "share_count",
            "amount",
            "gateway_name",
            "authority",
            "ref_id",
            "status",
            "status_display",
            "paid_at",
            "verified_at",
            "ip_address",
            "created_at",
        )
        read_only_fields = fields


# ===========================================================================
# Refund / adjustment serializers — admin financial controls
# ===========================================================================

class PaymentRefundSerializer(serializers.ModelSerializer):
    """Read serializer for refund workflow rows."""

    payment_authority = serializers.CharField(source="payment.authority", read_only=True)
    campaign_id = serializers.IntegerField(source="payment.participation.campaign_id", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)
    requested_by = AdminUserSummarySerializer(read_only=True)
    reviewed_by = AdminUserSummarySerializer(read_only=True)
    is_full_refund = serializers.BooleanField(read_only=True)

    class Meta:
        model = PaymentRefund
        fields = (
            "id",
            "payment",
            "payment_authority",
            "campaign_id",
            "requested_by",
            "reviewed_by",
            "amount",
            "reason",
            "reason_display",
            "status",
            "status_display",
            "idempotency_key",
            "provider_ref_id",
            "note",
            "rejection_reason",
            "is_full_refund",
            "reviewed_at",
            "completed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class PaymentRefundRequestSerializer(serializers.Serializer):
    """Input serializer for creating a payment refund request."""

    payment_id = serializers.IntegerField(min_value=1)
    amount = serializers.IntegerField(min_value=1)
    reason = serializers.ChoiceField(choices=RefundReason.choices, default=RefundReason.OTHER)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(required=False, allow_blank=True, default="")


class PaymentRefundRejectSerializer(serializers.Serializer):
    """Input serializer for rejecting a refund request."""

    rejection_reason = serializers.CharField(max_length=500)


class PaymentRefundCompleteSerializer(serializers.Serializer):
    """Input serializer for marking an approved refund as completed."""

    provider_ref_id = serializers.CharField(required=False, allow_blank=True, default="")


class FinancialAdjustmentSerializer(serializers.ModelSerializer):
    """Read serializer for campaign financial adjustment workflow rows."""

    campaign_title = serializers.CharField(source="campaign.title", read_only=True)
    payment_authority = serializers.CharField(source="payment.authority", read_only=True, allow_null=True)
    requested_by = AdminUserSummarySerializer(read_only=True)
    reviewed_by = AdminUserSummarySerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    adjustment_type_display = serializers.CharField(source="get_adjustment_type_display", read_only=True)
    signed_amount = serializers.IntegerField(read_only=True)

    class Meta:
        model = CampaignFinancialAdjustment
        fields = (
            "id",
            "campaign",
            "campaign_title",
            "payment",
            "payment_authority",
            "requested_by",
            "reviewed_by",
            "adjustment_type",
            "adjustment_type_display",
            "status",
            "status_display",
            "amount",
            "signed_amount",
            "reason",
            "note",
            "rejection_reason",
            "reviewed_at",
            "applied_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class FinancialAdjustmentCreateSerializer(serializers.Serializer):
    """Input serializer for creating a financial adjustment request."""

    campaign_id = serializers.IntegerField(min_value=1)
    payment_id = serializers.IntegerField(required=False, min_value=1, allow_null=True)
    adjustment_type = serializers.ChoiceField(choices=FinancialAdjustmentType.choices)
    amount = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=240)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class FinancialAdjustmentRejectSerializer(serializers.Serializer):
    """Input serializer for rejecting a financial adjustment request."""

    rejection_reason = serializers.CharField(max_length=500)


class CampaignFinancialControlSummarySerializer(serializers.Serializer):
    """Serializer for admin campaign financial-control summary."""

    campaign_id = serializers.IntegerField(read_only=True)
    gross_paid_amount = serializers.IntegerField(read_only=True)
    completed_refund_amount = serializers.IntegerField(read_only=True)
    completed_refund_count = serializers.IntegerField(read_only=True)
    applied_adjustment_delta = serializers.IntegerField(read_only=True)
    applied_adjustment_count = serializers.IntegerField(read_only=True)
    net_effective_amount = serializers.IntegerField(read_only=True)
    remaining_shares = serializers.IntegerField(read_only=True)


# ===========================================================================
# Risk signal serializers — admin financial safety
# ===========================================================================

class MadadkarRiskSignalSerializer(serializers.ModelSerializer):
    """Read serializer for Madadkar financial risk signals."""

    user = AdminUserSummarySerializer(read_only=True)
    campaign_title = serializers.CharField(source="campaign.title", read_only=True, allow_null=True)
    payment_authority = serializers.CharField(source="payment.authority", read_only=True, allow_null=True)
    signal_type_display = serializers.CharField(source="get_signal_type_display", read_only=True)
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    reviewed_by = AdminUserSummarySerializer(read_only=True)

    class Meta:
        model = MadadkarRiskSignal
        fields = (
            "id",
            "signal_type",
            "signal_type_display",
            "severity",
            "severity_display",
            "status",
            "status_display",
            "user",
            "campaign",
            "campaign_title",
            "payment",
            "payment_authority",
            "refund",
            "adjustment",
            "ip_address",
            "description",
            "metadata",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class MadadkarRiskSignalReviewSerializer(serializers.Serializer):
    """Input serializer for reviewing/dismissing/escalating risk signals."""

    status = serializers.ChoiceField(
        choices=(
            (MadadkarRiskStatus.REVIEWED, MadadkarRiskStatus.REVIEWED.label),
            (MadadkarRiskStatus.DISMISSED, MadadkarRiskStatus.DISMISSED.label),
            (MadadkarRiskStatus.ESCALATED, MadadkarRiskStatus.ESCALATED.label),
        ),
    )
    review_note = serializers.CharField(required=False, allow_blank=True, default="")


class MadadkarRiskSignalFilterSerializer(serializers.Serializer):
    """OpenAPI helper serializer for risk filters."""

    status = serializers.ChoiceField(choices=MadadkarRiskStatus.choices, required=False)
    severity = serializers.ChoiceField(choices=MadadkarRiskSeverity.choices, required=False)
    user = serializers.IntegerField(required=False, min_value=1)
    campaign = serializers.IntegerField(required=False, min_value=1)
    ip_address = serializers.IPAddressField(required=False)


# ===========================================================================
# Campaign intelligence serializers — admin decision support
# ===========================================================================

class CampaignDailyTrendSerializer(serializers.Serializer):
    """One day in campaign intelligence trend."""

    date = serializers.DateField(read_only=True)
    gross_amount = serializers.IntegerField(read_only=True)
    refund_amount = serializers.IntegerField(read_only=True)
    adjustment_delta = serializers.IntegerField(read_only=True)
    net_amount = serializers.IntegerField(read_only=True)
    successful_payments = serializers.IntegerField(read_only=True)


class CampaignIntelligenceSerializer(serializers.Serializer):
    """Admin campaign intelligence payload with financial, funnel, risk, and health metrics."""

    campaign_id = serializers.IntegerField(read_only=True)
    campaign_title = serializers.CharField(read_only=True)
    generated_at = serializers.DateTimeField(read_only=True)
    window_days = serializers.IntegerField(read_only=True)
    financials = serializers.JSONField(read_only=True)
    funnel = serializers.JSONField(read_only=True)
    velocity = serializers.JSONField(read_only=True)
    donor_concentration = serializers.JSONField(read_only=True)
    risk = serializers.JSONField(read_only=True)
    health = serializers.JSONField(read_only=True)
    daily_trend = CampaignDailyTrendSerializer(many=True, read_only=True)


class MadadkarIntelligenceOverviewSerializer(serializers.Serializer):
    """Portfolio-level Madadkar intelligence overview for command decisions."""

    generated_at = serializers.DateTimeField(read_only=True)
    window_days = serializers.IntegerField(read_only=True)
    portfolio = serializers.JSONField(read_only=True)
    weakest_campaigns = serializers.JSONField(read_only=True)
    strongest_campaigns = serializers.JSONField(read_only=True)


# ===========================================================================
# Donation receipt serializers — user/public/admin
# ===========================================================================

class DonationReceiptSerializer(serializers.ModelSerializer):
    """Read serializer for user-owned verifiable donation receipts."""

    campaign_title = serializers.CharField(source="campaign.title", read_only=True)
    campaign_slug = serializers.CharField(source="campaign.slug", read_only=True)

    class Meta:
        model = DonationReceipt
        fields = (
            "id",
            "receipt_number",
            "receipt_hash",
            "hash_version",
            "amount",
            "issued_at",
            "campaign",
            "campaign_title",
            "campaign_slug",
            "payment_snapshot",
            "campaign_snapshot",
            "donor_snapshot",
            "resend_count",
            "last_resent_at",
            "created_at",
        )
        read_only_fields = fields


class DonationReceiptPublicVerifySerializer(serializers.Serializer):
    """Input serializer for public receipt verification."""

    receipt_number = serializers.CharField(max_length=40)
    receipt_hash = serializers.CharField(min_length=64, max_length=64)


class DonationReceiptVerificationResultSerializer(serializers.Serializer):
    """Public-safe receipt verification result."""

    is_valid = serializers.BooleanField(read_only=True)
    receipt_number = serializers.CharField(read_only=True)
    amount = serializers.IntegerField(read_only=True, allow_null=True)
    issued_at = serializers.DateTimeField(read_only=True, allow_null=True)
    campaign_title = serializers.CharField(read_only=True, allow_blank=True)
    sponsor_name = serializers.CharField(read_only=True, allow_blank=True)
    hash_version = serializers.IntegerField(read_only=True, allow_null=True)


class DonationReceiptResendSerializer(serializers.Serializer):
    """Empty serializer for documenting receipt resend action."""

    delivery_channel = serializers.ChoiceField(
        choices=(("email", "email"), ("in_app", "in_app")),
        required=False,
        default="email",
    )


# ===========================================================================
# Reconciliation serializers — admin settlement operations
# ===========================================================================

class PaymentReconciliationBatchSerializer(serializers.ModelSerializer):
    """Read serializer for provider settlement reconciliation batches."""

    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = PaymentReconciliationBatch
        fields = (
            "id",
            "provider_name",
            "source_name",
            "status",
            "status_display",
            "total_rows",
            "matched_count",
            "mismatch_count",
            "missing_internal_count",
            "duplicate_provider_ref_count",
            "summary",
            "completed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class PaymentReconciliationItemSerializer(serializers.ModelSerializer):
    """Read serializer for one provider/internal reconciliation comparison row."""

    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = PaymentReconciliationItem
        fields = (
            "id",
            "batch",
            "payment",
            "authority",
            "provider_ref_id",
            "provider_amount",
            "provider_status",
            "internal_amount",
            "internal_status",
            "status",
            "status_display",
            "reason",
            "raw_payload",
            "created_at",
        )
        read_only_fields = fields


class PaymentReconciliationImportSerializer(serializers.Serializer):
    """Input serializer for uploading a provider settlement report."""

    provider_name = serializers.CharField(max_length=50)
    source_name = serializers.CharField(required=False, allow_blank=True, default="")
    file = serializers.FileField()

    def validate_file(self, uploaded_file):
        """Validate settlement file extension before parser-level validation."""
        name = uploaded_file.name.lower()
        if not name.endswith((".csv", ".xlsx")):
            raise serializers.ValidationError("فایل تطبیق باید CSV یا XLSX باشد.")
        return uploaded_file


# ===========================================================================
# Disbursement serializers — admin allocation ledger
# ===========================================================================

class CampaignDisbursementSerializer(serializers.ModelSerializer):
    """Read serializer for campaign fund disbursement workflow rows."""

    campaign_title = serializers.CharField(source="campaign.title", read_only=True)
    requested_by = AdminUserSummarySerializer(read_only=True)
    reviewed_by = AdminUserSummarySerializer(read_only=True)
    paid_by = AdminUserSummarySerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = CampaignDisbursement
        fields = (
            "id",
            "campaign",
            "campaign_title",
            "requested_by",
            "reviewed_by",
            "paid_by",
            "status",
            "status_display",
            "amount",
            "recipient_name",
            "recipient_identifier",
            "recipient_bank_account",
            "recipient_snapshot",
            "purpose",
            "note",
            "rejection_reason",
            "bank_tracking_reference",
            "supporting_document",
            "approved_at",
            "rejected_at",
            "paid_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class CampaignDisbursementCreateSerializer(serializers.Serializer):
    """Input serializer for requesting a campaign disbursement."""

    campaign_id = serializers.IntegerField(min_value=1)
    amount = serializers.IntegerField(min_value=1)
    recipient_name = serializers.CharField(max_length=220)
    recipient_identifier = serializers.CharField(required=False, allow_blank=True, default="")
    recipient_bank_account = serializers.CharField(required=False, allow_blank=True, default="")
    purpose = serializers.CharField(max_length=260)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    supporting_document = serializers.JSONField(required=False, default=dict)


class CampaignDisbursementRejectSerializer(serializers.Serializer):
    """Input serializer for rejecting a requested disbursement."""

    rejection_reason = serializers.CharField(max_length=500)


class CampaignDisbursementMarkPaidSerializer(serializers.Serializer):
    """Input serializer for marking approved disbursement as paid."""

    bank_tracking_reference = serializers.CharField(max_length=120)


class CampaignDisbursableSummarySerializer(serializers.Serializer):
    """Serializer for campaign disbursable amount summary."""

    campaign_id = serializers.IntegerField(read_only=True)
    net_effective_amount = serializers.IntegerField(read_only=True)
    committed_disbursement_amount = serializers.IntegerField(read_only=True)
    paid_disbursement_amount = serializers.IntegerField(read_only=True)
    disbursable_amount = serializers.IntegerField(read_only=True)
