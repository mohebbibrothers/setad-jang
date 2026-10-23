"""فرم‌های پنل مددکار — به‌ویژه ورود تاریخ انعطاف‌پذیر و فرم‌های تأمین خارجی.

چرا FlexiblePersianDateTimeField؟
    ادمینِ واقعی تاریخ را به هزار شکل وارد می‌کند: ISO، اسلش، ارقام فارسی،
    و مهم‌تر از همه **جلالی**. فرمت پیش‌فرض لوکال fa-ir جنگو هیچ‌کدام را
    نمی‌پذیرفت و POST ادمین با خطای «این مقدار لازم است» برمی‌گشت
    (باگ گزارش‌شده‌ی ۵۰۰/خطای ذخیره). این فیلد همه‌ی این صورت‌ها را
    با یک قاعده‌ی شفاف می‌پذیرد:

      سال >= 1300 → جلالی  (۱۴۰۵/۰۸/۰۱)
      سال >= 1700 → میلادی (2026-10-23)

    تبدیل جلالی→میلادی با الگوریتم کلاسیک و بدون وابستگی خارجی است.
"""

from __future__ import annotations

import re
from datetime import datetime

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_DATE_RE = re.compile(
    r"^\s*(\d{3,4})[-/.](\d{1,2})[-/.](\d{1,2})"
    r"(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?\s*$"
)


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    """تبدیل جلالی به میلادی — الگوریتم کلاسیک خیّام (جی‌دی‌ان).

    مرجع اعتبارسنجی (تست‌ها): ۱۴۰۵/۰۸/۰۱ ≡ 2026-10-23
    """
    jy += 1595
    days = -355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += ((jm - 7) * 30) + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)
    for i, dim in enumerate([31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]):
        if gd <= dim:
            return gy, i + 1, gd
        gd -= dim
    raise ValueError("تاریخ جلالی نامعتبر است")


class FlexiblePersianDateTimeField(forms.DateTimeField):
    """DateTime سازگار — ISO/اسلش/ارقام فارسی/جلالی."""

    default_error_messages = {
        "invalid": (
            "تاریخ معتبر نیست. نمونه‌های پذیرفته‌شده: "
            "2026-10-23 10:00 یا 1405/08/01 12:30 (ارقام فارسی هم آزاد است)."
        ),
    }

    def to_python(self, value):
        """پارسِ چندفرمته؛ رشته‌ی خالی = None (اختیاری در فرم)."""
        if value in self.empty_values:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).translate(_PERSIAN_DIGITS).replace("T", " ").strip()
        m = _DATE_RE.match(text)
        if not m:
            raise ValidationError(self.error_messages["invalid"], code="invalid")
        year, month, day = (int(m.group(i)) for i in (1, 2, 3))
        hour = int(m.group(4) or 0)
        minute = int(m.group(5) or 0)
        second = int(m.group(6) or 0)
        try:
            if 1300 <= year <= 1600:
                year, month, day = jalali_to_gregorian(year, month, day)
            naive = datetime(year, month, day, hour, minute, second)
        except (ValueError, OverflowError) as exc:
            raise ValidationError(self.error_messages["invalid"], code="invalid") from exc
        return timezone.make_aware(naive) if timezone.is_naive(naive) else naive


class ExternalFundingFormBase(forms.ModelForm):
    """پایه‌ی مشترک فرم‌های تأمین خارجی — بدون وابستگی به سطح پنل."""

    funded_at = FlexiblePersianDateTimeField(
        required=False,
        label="تاریخ دریافت خارج از سایت",
        help_text="خالی بگذارید = همین الان ثبت می‌شود • میلادی یا جلالی (مثل ۱۴۰۵/۰۸/۰۱)",
    )

    class Meta:
        from apps.madadkar.models import ExternalFunding

        model = ExternalFunding
        fields = ("shares", "amount", "method", "reference", "funded_at", "note")
        labels = {
            "reference": "شماره پیگیری / فیش (اختیاری)",
            "note": "یادداشت داخلی (اختیاری)",
        }
        help_texts = {
            "amount": "خالی بگذارید تا به‌صورت خودکار سهم × قیمت سهم محاسبه شود.",
        }
        widgets = {
            "reference": forms.TextInput(attrs={"placeholder": "اختیاری — مثلاً ۲۴۵۶۷۸"}),
            "note": forms.Textarea(attrs={"rows": 2, "placeholder": "اختیاری — جزئیات داخلی ثبت"}),
            "amount": forms.NumberInput(attrs={"min": 1}),
            "shares": forms.NumberInput(attrs={"min": 1}),
        }

    def _set_remaining_guidance(self, remaining: int) -> None:
        """راهنمای زنده‌ی سقف روی فیلد سهم — حلِ ابهام ادمین."""
        field = self.fields["shares"]
        field.help_text = (
            f"باقی‌مانده‌ی قابل ثبت: {remaining:,} سهم "
            "(برای تأمینِ کاملِ حرکت از بیرون، همین عدد را وارد کنید)"
        )
        field.widget.attrs["max"] = remaining
        field.widget.attrs["placeholder"] = f"حداکثر {remaining:,}"

    def clean(self):
        cleaned = super().clean()
        shares = cleaned.get("shares")
        amount = cleaned.get("amount")
        campaign = self._resolve_campaign(cleaned)

        if campaign is not None:
            from apps.madadkar.choices import CampaignStatus

            if campaign.status not in (CampaignStatus.DRAFT, CampaignStatus.PUBLISHED):
                self.add_error(
                    "campaign" if "campaign" in self.fields else "shares",
                    "ثبت تأمین خارجی فقط برای حرکت‌های پیش‌نویس یا منتشرشده ممکن است.",
                )

        if shares is not None and shares < 1:
            self.add_error("shares", "تعداد سهم باید حداقل ۱ باشد.")
        elif campaign is not None and shares is not None and shares > campaign.remaining_shares:
            self.add_error(
                "shares",
                f"سقف قابل ثبت {campaign.remaining_shares:,} سهم است "
                "(باقی‌مانده پس از احتساب رزروهای آنلاین و تأمین‌های خارجی قبلی).",
            )
        if amount is not None and amount < 1:
            self.add_error("amount", "مبلغ دریافتی نمی‌تواند صفر یا منفی باشد.")
        return cleaned

    def _resolve_campaign(self, cleaned):
        """کمپین را از داده‌ی تمیزشده، initial یا POST خام پیدا می‌کند."""
        campaign = cleaned.get("campaign")
        if campaign is not None:
            return campaign
        from apps.madadkar.models import Campaign

        for source in (
            self.initial.get("campaign"),
            (self.data.get("campaign") if self.is_bound else None),
        ):
            if not source:
                continue
            try:
                if isinstance(source, Campaign):
                    return source
                return Campaign.objects.get(pk=int(source))
            except (Campaign.DoesNotExist, ValueError, TypeError):
                continue
        return None


class ExternalFundingAddForm(ExternalFundingFormBase):
    """فرم افزودن مستقل — شامل انتخاب حرکت + راهنمای سقفِ لحظه‌ای."""

    class Meta(ExternalFundingFormBase.Meta):
        fields = ("campaign", "shares", "amount", "method", "reference", "funded_at", "note")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["campaign"].help_text = (
            "پیشنهاد: از ستون «+ ثبت تأمین خارجی» در لیست حرکت‌ها بیایید تا "
            "حرکت از قبل انتخاب و سقف دقیق نمایش داده شود."
        )
        campaign = self._resolve_campaign({}) if (self.is_bound or self.initial) else None
        if campaign is not None:
            self._set_remaining_guidance(campaign.remaining_shares)


class ExternalFundingInlineForm(ExternalFundingFormBase):
    """فرم اینلاین صفحه‌ی حرکت — کمپین والد از طریق get_formset تزریق می‌شود."""

    _campaign = None

    def _resolve_campaign(self, cleaned):
        return self._campaign
