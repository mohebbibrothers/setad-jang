"""Django Admin دیوار مهربانی (v2) — اتاق فرمان ادمین.

چهار ModelAdmin: دسته، آگهی (با inline تصاویر و اکشن‌های چرخه حیات + خروجی
اکسل)، تصویر (پنهان از ایندکس، لینک مستقیم/عیب‌یابی)، اعلام آمادگی (تریاج).
اکشن‌ها مستقیماً از services می‌گذرند تا اعتبار سیاست یکجا اعمال شود و
audit هم ثبت گردد.
"""

from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.db.models import Q
from django.http import HttpResponse
from django.template.defaultfilters import truncatechars
from django.utils import timezone
from django.utils.html import format_html

from apps.audit_logs.services import log_action_async
from apps.core.geo import PROVINCE_NAMES, cities_of, localities_of
from apps.kindness_wall import services
from apps.kindness_wall.choices import MAX_IMAGES_PER_LISTING, ListingStatus, OfferStatus, Urgency
from apps.kindness_wall.export import (
    build_kindness_export_filename,
    build_listings_workbook,
)
from apps.kindness_wall.models import (
    KindnessCategory,
    KindnessListing,
    KindnessListingImage,
    KindnessOffer,
)


class HiddenFromAdminIndexMixin:
    """مدل ثبت‌شده می‌ماند ولی در فهرست ایندکس ادمین دیده نمی‌شود."""

    def get_model_perms(self, request) -> dict[str, bool]:
        """بدون perms یعنی حذف از ایندکس — الگوی مشترک r4j/tabyin."""
        return {}


_STATUS_COLORS = {
    ListingStatus.DRAFT: "#8a8a8a",
    ListingStatus.PUBLISHED: "#1a7f37",
    ListingStatus.FULFILLED: "#7A277A",
    ListingStatus.EXPIRED: "#c2410c",
    ListingStatus.ARCHIVED: "#475569",
}

_OFFER_COLORS = {
    OfferStatus.NEW: "#b45309",
    OfferStatus.CONTACTED: "#1d4ed8",
    OfferStatus.DECLINED: "#991b1b",
}


def _badge(text: str, color: str) -> object:
    """پیل رنگی خوانات در list_display (سبک ادمین احراز هویت)."""
    return format_html('<strong style="color: {};">{}</strong>', color, text)


@admin.register(KindnessCategory)
class KindnessCategoryAdmin(admin.ModelAdmin):
    """taxonomy دیوار: ساخت/ویرایش دسته‌ها توسط ادمین."""

    list_display = ("title", "icon", "order", "open_count", "active_flag", "updated_at")
    list_editable = ("order",)
    search_fields = ("title", "slug", "description")
    ordering = ("order", "title")
    readonly_fields = ("slug", "created_at", "updated_at")
    actions = ("activate_categories", "deactivate_categories")

    @admin.display(description="آگهی جاری")
    def open_count(self, obj: KindnessCategory) -> object:
        """شمار زندهٔ آگهی‌های جاری این دسته روی تخته."""
        count = obj.open_listings().count()
        color = "#1a7f37" if count else "#8a8a8a"
        return format_html("<strong style='color: {};'>{}</strong>", color, count)

    @admin.display(description="فعال", boolean=True)
    def active_flag(self, obj: KindnessCategory) -> bool:
        """is_active با عنوان فارسی در سرتیر."""
        return obj.is_active

    @admin.action(description="فعال‌سازی دسته‌های انتخاب‌شده")
    def activate_categories(self, request, queryset) -> None:
        """فعال‌سازی گروهی (بدون نگهبان؛ بازکردن همیشه امن است)."""
        updated = queryset.update(is_active=True, updated_at=timezone.now())
        messages.success(request, f"{updated} دسته فعال شد.")

    @admin.action(description="غیرفعال‌سازی دسته‌های انتخاب‌شده")
    def deactivate_categories(self, request, queryset) -> None:
        """غیرفعال‌سازی گروهی با نگهبان «آگهی جاری نداشته باشد»."""
        blocked = 0
        done = 0
        for category in queryset:
            try:
                services.set_category_active(category=category, active=False)
                done += 1
            except services.KindnessCategoryGuardError:
                blocked += 1
        if done:
            messages.success(request, f"{done} دسته غیرفعال شد.")
        if blocked:
            messages.warning(
                request,
                f"{blocked} دسته آگهی جاری دارد و غیرفعال نشد؛ ابتدا تکلیف آگهی‌ها را روشن کنید.",
            )

    def save_model(self, request, obj, form, change) -> None:
        """ثبت audit برای ساخت/ویرایش دسته."""
        super().save_model(request, obj, form, change)
        log_action_async(
            user_id=request.user.pk,
            action="KINDNESS_CATEGORY_UPDATED" if change else "KINDNESS_CATEGORY_CREATED",
            resource_type="kindness_category",
            resource_id=str(obj.pk),
            changes={"title": obj.title},
        )


class KindnessListingImageInline(admin.TabularInline):
    """تصاویر آگهی داخل فرم؛ کاور خودکار با منطق model."""

    model = KindnessListingImage
    extra = 0
    max_num = MAX_IMAGES_PER_LISTING
    fields = ("image", "alt_text", "is_cover", "order")


class KindnessListingAdminForm(forms.ModelForm):
    """فرمِ آگهی با دراپ‌دانِ وابستهٔ استان → شهر (و راهنمای روستا).

    • «شهر» به `<select>` تبدیل می‌شود با گزینه‌های همان استان؛ اعتبارسنجیِ
      نهایی همچنان در `clean()` مدل و `validate_iran_place` است، پس دستکاریِ
      POST هم پاسخِ صریح می‌گیرد.
    • مقدارِ فعلی همیشه در فهرست می‌ماند تا ویرایشِ رکوردِ قدیمی چیزی را از
      دست ندهد (حتی اگر شهر بیرون از دیتاست باشد، با برچسبِ هشدار نمایش
      داده می‌شود و ادمین می‌تواند اصلاحش کند).
    """

    class Meta:
        model = KindnessListing
        # همهٔ فیلدهای ویرایش‌پذیر صریح (قاعدهٔ DJ007: `__all__` در ModelForm ممنوع)
        fields = (
            "category",
            "title",
            "description",
            "quantity",
            "unit",
            "urgency",
            "is_featured",
            "beneficiary_name",
            "province",
            "city",
            "locality",
            "contact_phone",
            "contact_bale",
            "contact_eitaa",
            "contact_telegram",
            "contact_rubika",
            "contact_instagram",
            "contact_note",
            "status",
            "expires_at",
            "fulfillment_note",
            "is_active",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        province_field = self.fields.get("province")
        if province_field is not None:
            # خودِ مدل choices دارد؛ صریح می‌گذاریم تا ویجت هم قطعی باشد.
            province_field.widget = forms.Select(
                choices=[("", "— سراسر کشور (بدونِ استان) —")]
                + [(name, name) for name in PROVINCE_NAMES()]
            )

        city_field = self.fields.get("city")
        if city_field is None:
            return

        province_value = ""
        if self.is_bound:
            province_value = (self.data.get("province") or "").strip()
        elif self.instance and self.instance.pk:
            province_value = (self.instance.province or "").strip()

        choices: list[tuple[str, str]] = [("", "— همهٔ شهرهای استان / سراسر کشور —")]
        if province_value:
            choices += [(city, city) for city in cities_of(province_value)]
            current = ""
            if self.is_bound:
                current = (self.data.get("city") or "").strip()
            elif self.instance and self.instance.pk:
                current = (self.instance.city or "").strip()
            if current and current not in {value for value, _label in choices}:
                choices.append((current, f"{current} (خارج از فهرستِ رسمی)"))
        city_field.widget = forms.Select(choices=choices)

        locality_field = self.fields.get("locality")
        if locality_field is not None:
            locality_field.widget.attrs.setdefault("list", "kw-locality-options")


@admin.register(KindnessListing)
class KindnessListingAdmin(admin.ModelAdmin):
    """آلات اصلی مدیریت دیوار: ویرایش آگهی + چرخه حیات + خروجی."""

    form = KindnessListingAdminForm

    class Media:
        """اسکریپتِ وابسته‌سازیِ استان→شهر (بدونِ وابستگی به jQuery ادمین)."""

        js = ("kindness_wall/admin_geo.js",)

    list_display = (
        "title_short",
        "category",
        "status_badge",
        "urgency_flag",
        "featured_star",
        "location_badge",
        "expires_display",
        "view_count",
        "offer_count_badge",
    )
    list_filter = ("status", "urgency", "category", "is_featured", "is_active")
    search_fields = (
        "title",
        "description",
        "contact_phone",
        "contact_telegram",
        "beneficiary_name",
    )
    ordering = ("-created_at",)
    autocomplete_fields = ("category",)
    readonly_fields = (
        "slug",
        "view_count",
        "renew_count",
        "published_at",
        "fulfilled_at",
        "fulfillment_note",
        "created_by",
        "created_at",
        "updated_at",
        "contact_channels_readonly",
    )
    inlines = [KindnessListingImageInline]
    actions = (
        "publish_listings",
        "renew_listings",
        "fulfill_listings",
        "archive_listings",
        "revert_to_draft",
        "export_listings_xlsx",
    )
    fieldsets = (
        (
            "محتوا",
            {
                "fields": (
                    "category",
                    "title",
                    "description",
                    "quantity",
                    "unit",
                    "urgency",
                    "is_featured",
                )
            },
        ),
        (
            "صاحبِ نیاز و موقعیتِ جغرافیایی",
            {
                "description": (
                    "نام/لقبِ صاحبِ نیاز (می‌تواند محرمانه باشد) و محلِ برآورده‌شدنِ نیاز. "
                    "استان را از فهرست انتخاب کنید تا فهرستِ شهرهای همان استان باز شود؛ "
                    "خالی گذاشتنِ استان یعنی «سراسر کشور» — چنین آگهی‌ای در فیلترِ هر "
                    "استان و شهری هم به کاربر نشان داده می‌شود."
                ),
                "fields": ("beneficiary_name", "province", "city", "locality"),
            },
        ),
        (
            "راه‌های تماس (حداقل یکی برای انتشار — همه می‌توانند پر شوند)",
            {
                "description": (
                    "این کانال‌ها دقیقاً در همان آگهی به کاربر نمایش داده می‌شوند و تماس "
                    "خارج از اپ انجام می‌شود. مقادیر خودکار نرمال می‌شوند (۰۹۸→۰، حذف @ و دامنه)."
                ),
                "fields": (
                    "contact_phone",
                    "contact_bale",
                    "contact_eitaa",
                    "contact_telegram",
                    "contact_rubika",
                    "contact_instagram",
                    "contact_note",
                ),
            },
        ),
        (
            "وضعیت و چرخه حیات",
            {
                "fields": (
                    "status",
                    "published_at",
                    "expires_at",
                    "renew_count",
                    "contact_channels_readonly",
                ),
            },
        ),
        (
            "برطرف‌شدن (روایت بایگانی)",
            {
                "fields": ("fulfilled_at", "fulfillment_note"),
                "classes": ("collapse",),
            },
        ),
        (
            "داده‌های سیستمی",
            {
                "fields": ("slug", "view_count", "created_by", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """نقشهٔ استان→شهر (و روستاها) را در قالبِ فرم تزریق می‌کند.

        فقط استان‌هایی که شهر دارند فرستاده می‌شوند تا حجمِ HTML کم بماند؛
        `admin_geo.js` همین ساختار را می‌خواند.
        """
        extra_context = {**(extra_context or {})}
        extra_context["geo_data"] = {
            "cities": {name: cities_of(name) for name in PROVINCE_NAMES()},
            "localities": {name: localities_of(name) for name in PROVINCE_NAMES()},
        }
        return super().changeform_view(request, object_id, form_url, extra_context)

    @admin.display(description="عنوان")
    def title_short(self, obj: KindnessListing) -> str:
        """عنوان بریده‌شده برای خوانایی فهرست."""
        return truncatechars(obj.title, 60)

    @admin.display(description="وضعیت")
    def status_badge(self, obj: KindnessListing) -> object:
        """پیل رنگی وضعیت (سبز=جاری، بنفش=برطرف، ...)."""
        return _badge(obj.get_status_display(), _STATUS_COLORS.get(obj.status, "#333"))

    @admin.display(description="فوریت", ordering="urgency")
    def urgency_flag(self, obj: KindnessListing) -> object:
        """🔔 برای فوری؛ خالی برای عادی."""
        if obj.urgency == Urgency.URGENT:
            return format_html("🔔 <strong>{}</strong>", "فوری")
        return "—"

    @admin.display(description="ویژه", ordering="is_featured")
    def featured_star(self, obj: KindnessListing) -> str:
        """⭐ برای آگهی تثبیت‌شده بالای دیوار."""
        return "⭐" if obj.is_featured else ""

    @admin.display(description="موقعیت", ordering="province")
    def location_badge(self, obj: KindnessListing) -> object:
        """موقعیتِ خوانا: روستا/شهر، استان — یا نشانِ «سراسر کشور»."""
        if not (obj.province or "").strip():
            return format_html(
                "<span style='display:inline-block;padding:1px 8px;border-radius:999px;"
                "background:#0d8074;color:#fff;font-size:11px;'>سراسر کشور</span>"
            )
        parts = [p for p in (obj.locality, obj.city, obj.province) if (p or "").strip()]
        return "، ".join(parts)

    @admin.display(description="انقضا", ordering="expires_at")
    def expires_display(self, obj: KindnessListing) -> object:
        """انقضا با هشدار رنگی نزدیک-به-مرگ."""
        if obj.expires_at is None:
            return "بدون انقضا"
        days = obj.days_left
        if days is None:
            return "—"
        color = "#c2410c" if days <= 7 else "#374151"
        return format_html(
            "<span style='color: {};'>{} — {} روز مانده</span>",
            color,
            timezone.localtime(obj.expires_at).strftime("%Y-%m-%d"),
            days,
        )

    @admin.display(description="اعلام‌ها", ordering="view_count")
    def offer_count_badge(self, obj: KindnessListing) -> object:
        """شمار اعلام‌های باز روی همان آگهی (دعوت به تریاج)."""
        total = obj.offers.filter(status=OfferStatus.NEW).count()
        if not total:
            return "۰"
        return format_html("<strong style='color: #b45309;'>{} باز</strong>", total)

    @admin.display(description="کانال‌های فعال")
    def contact_channels_readonly(self, obj: KindnessListing) -> str:
        """نمایش خلاصه کانال‌های پرشده در فرم (read-only؛ ویرایش از فیلدها)."""
        if obj.pk is None:
            return "پس از ذخیره آگهی محاسبه می‌شود."
        payload = obj.channel_payload()
        if not payload:
            return "هنوز هیچ راه تماسی پر نشده — انتشار مسدود است."
        return "، ".join(f"{item['label']}: {item['value']}" for item in payload)

    def get_queryset(self, request):
        """پیش‌فرض: تازه‌ترین‌ها؛ select_related برای حذف N+1 شمارش اعلام."""
        return super().get_queryset(request).select_related("category")

    def save_model(self, request, obj, form, change) -> None:
        """ذخیره با ثبت creator (برای ممیزی) و audit."""
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        log_action_async(
            user_id=request.user.pk,
            action="KINDNESS_LISTING_UPDATED" if change else "KINDNESS_LISTING_CREATED",
            resource_type="kindness_listing",
            resource_id=str(obj.pk),
            changes={"title": obj.title, "status": obj.status},
        )

    def _run_service(
        self, request, queryset, service_name: str, audit_action: str, *, ok_verb: str
    ) -> None:
        """اجرای گروهی یک سرویس وضعیت روی selection با گزارش موفق/ناموفق."""
        fn = getattr(services, service_name)
        done, failed = 0, 0
        for listing in queryset:
            try:
                fn(listing=listing)
                done += 1
                log_action_async(
                    user_id=request.user.pk,
                    action=audit_action,
                    resource_type="kindness_listing",
                    resource_id=str(listing.pk),
                    changes={"status": listing.status},
                )
            except services.KindnessWallServiceError as exc:
                failed += 1
                messages.error(request, f"«{listing.title}»: {exc}")
        if done:
            messages.success(
                request, f"{done} آگهی {ok_verb} شد." + (f" ({failed} خطا)" if failed else "")
            )
        elif failed:
            messages.warning(request, "هیچ آگهی تغییر نکرد؛ پیام‌های خطا را ببینید.")

    @admin.action(description="انتشار روی دیوار (بررسی حداقل یک راه تماس)")
    def publish_listings(self, request, queryset) -> None:
        """انتشار گروهی از مسیر publish_listing (قاعدهٔ تماس اینجا قفل است)."""
        self._run_service(
            request, queryset, "publish_listing", "KINDNESS_LISTING_PUBLISHED", ok_verb="منتشر"
        )

    @admin.action(description="تمدید مهلت آگهی‌های انتخاب‌شده")
    def renew_listings(self, request, queryset) -> None:
        """تمدید گروهی (بازنشانی expires_at از امروز + شمارنده renew)."""
        self._run_service(
            request, queryset, "renew_listing", "KINDNESS_LISTING_RENEWED", ok_verb="تمدید"
        )

    @admin.action(description="برطرف شد (ثبت روایت در بایگانی)")
    def fulfill_listings(self, request, queryset) -> None:
        """برطرف‌سازی گروهی بدون روایت؛ برای روایت، ویرایش تکی را ببینید."""
        self._run_service(
            request,
            queryset,
            "fulfill_listing",
            "KINDNESS_LISTING_FULFILLED",
            ok_verb="برطرف‌شده ثبت",
        )

    @admin.action(description="بایگانی آگهی‌های انتخاب‌شده")
    def archive_listings(self, request, queryset) -> None:
        """بایگانی گروهی (حذف فیزیکی نمی‌شود؛ لینک‌ها سالم می‌مانند)."""
        self._run_service(
            request, queryset, "archive_listing", "KINDNESS_LISTING_ARCHIVED", ok_verb="بایگانی"
        )

    @admin.action(description="بازگرداندن به پیش‌نویس")
    def revert_to_draft(self, request, queryset) -> None:
        """هر وضعیتی → draft (برای ویرایش مجدد پیش از انتشار)."""
        self._run_service(
            request,
            queryset,
            "revert_to_draft",
            "KINDNESS_LISTING_REVERTED_TO_DRAFT",
            ok_verb="به پیش‌نویس بازگشت",
        )

    @admin.action(description="خروجی اکسل از انتخاب (یا کل فیلترشده)")
    def export_listings_xlsx(self, request, queryset) -> object:
        """ساخت شیت از queryset فیلترشدهٔ ادمین و ارسال به‌عنوان دانلود."""
        workbook = build_listings_workbook(
            listings=queryset.order_by("-created_at").iterator(chunk_size=1000)
        )
        log_action_async(
            user_id=request.user.pk,
            action="KINDNESS_LISTINGS_EXPORTED",
            resource_type="kindness_listing",
            changes={"row_count": queryset.count()},
        )
        response = HttpResponse(
            workbook.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        filename = build_kindness_export_filename(export_type="listings")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        workbook.close()
        return response


@admin.register(KindnessOffer)
class KindnessOfferAdmin(admin.ModelAdmin):
    """تریاج اعلام‌های آمادگی: وضعیت، یادداشت، خروجی."""

    list_display = ("user", "listing", "status_badge", "created_at", "handled_display")
    list_filter = ("status",)
    search_fields = ("listing__title", "user__username", "user__email", "message")
    autocomplete_fields = ("listing",)
    date_hierarchy = "created_at"
    readonly_fields = ("listing", "user", "message", "created_at", "handled_by", "handled_at")
    actions = ("mark_contacted", "mark_declined")
    list_select_related = ("listing", "user", "handled_by")

    @admin.display(description="وضعیت پیگیری")
    def status_badge(self, obj: KindnessOffer) -> object:
        """پیل وضعیت اعلام آمادگی."""
        return _badge(obj.get_status_display(), _OFFER_COLORS.get(obj.status, "#333"))

    @admin.display(description="بررسی")
    def handled_display(self, obj: KindnessOffer) -> str:
        """خلاصه «چه کسی کی» در فهرست."""
        if obj.handled_at is None:
            return "در انتظار"
        return f"{getattr(obj.handled_by, 'full_name', None) or obj.handled_by} · {timezone.localtime(obj.handled_at):%Y-%m-%d}"

    def get_actions(self, request):
        """حذف گروهی خاموش — سوابق پیگیری نباید پاک شوند؛ «رد شد» بزنید."""
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def has_delete_permission(self, request, obj=None) -> bool:
        """حذف تکی هم ممنوع (انضباط دادهٔ سابقهٔ تریاج)."""
        return False

    def _review(self, request, queryset, status: str) -> None:
        """ثبت گروهی نتیجهٔ بررسی با audit."""
        done = 0
        for offer in queryset:
            try:
                services.review_offer(offer=offer, admin=request.user, status=status)
            except services.KindnessWallServiceError:
                continue
            done += 1
            log_action_async(
                user_id=request.user.pk,
                action="KINDNESS_OFFER_REVIEWED",
                resource_type="kindness_offer",
                resource_id=str(offer.pk),
                changes={"status": status},
            )
        messages.success(request, f"{done} اعلام آمادگی ثبت نتیجه شد.")

    @admin.action(description="علامت‌گذاری: تماس گرفته شد")
    def mark_contacted(self, request, queryset) -> None:
        """پیگیری موفق: با داوطلب تماس گرفته/استفاده شد."""
        self._review(
            request, queryset.filter(~Q(status=OfferStatus.CONTACTED)), OfferStatus.CONTACTED
        )

    @admin.action(description="علامت‌گذاری: رد شد")
    def mark_declined(self, request, queryset) -> None:
        """نیاز پر شد یا داوطلب مناسب نبود."""
        self._review(
            request, queryset.filter(~Q(status=OfferStatus.DECLINED)), OfferStatus.DECLINED
        )


@admin.register(KindnessListingImage)
class KindnessListingImageAdmin(HiddenFromAdminIndexMixin, admin.ModelAdmin):
    """مدیریت مستقیم تصاویر (عیب‌یابی/جابه‌جایی کاور) — لینکی از ایندکس نیست."""

    list_display = ("listing", "image", "is_cover", "order", "created_at")
    list_filter = ("is_cover",)
    search_fields = ("listing__title",)
    autocomplete_fields = ("listing",)
