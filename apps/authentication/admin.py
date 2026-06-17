"""
Django admin configuration for users, profiles, and OTP records.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import AuthSession, OTPCode, Profile, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """
    UserAdmin سفارشی هماهنگ با multi-identifier model.

    - email و phone_number هر دو در list_display و search_fields هستند.
    - primary_identifier نشان می‌دهد کاربر در ابتدا با کدام channel signup کرده.
    - is_email_verified و is_phone_verified به‌صورت مستقل قابل مدیریت هستند.
    """

    ordering = ("-date_joined",)
    list_display = (
        "email",
        "phone_number",
        "primary_identifier",
        "first_name",
        "last_name",
        "role",
        "is_active",
        "is_email_verified",
        "is_phone_verified",
        "date_joined",
    )
    list_filter = (
        "role",
        "primary_identifier",
        "is_active",
        "is_email_verified",
        "is_phone_verified",
        "is_staff",
    )
    search_fields = ("email", "phone_number", "first_name", "last_name")
    readonly_fields = ("date_joined", "last_login", "last_login_ip")

    fieldsets = (
        (None, {"fields": ("email", "phone_number", "primary_identifier", "password")}),
        ("اطلاعات شخصی", {"fields": ("first_name", "last_name")}),
        (
            "نقش و دسترسی",
            {
                "fields": (
                    "role",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "is_email_verified",
                    "is_phone_verified",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("اطلاعات سیستم", {"fields": ("date_joined", "last_login", "last_login_ip")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "role",
                    "is_staff",
                    "is_active",
                ),
            },
        ),
    )


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    """
    ProfileAdmin پس از refactor — فیلد phone_number حذف شده است.
    شماره موبایل اکنون در سطح User نگه‌داری می‌شود.
    """

    list_display = ("user", "national_code", "city")
    search_fields = ("user__email", "user__phone_number", "national_code")


@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    """
    OTPCodeAdmin پس از Phase D refactor.

    - identifier_kind و identifier_value به جای user FK.
    - code_hash نه plain code (در پنل نمایش داده می‌شود ولی readonly است
      و حتی hash هم برای debug تنها ارزش محدود دارد).
    - attempts برای مشاهده‌ی الگوهای brute-force.
    """

    list_display = (
        "identifier_kind",
        "identifier_value",
        "purpose",
        "attempts",
        "is_used",
        "expires_at",
        "created_at",
    )
    list_filter = ("identifier_kind", "purpose", "is_used")
    search_fields = ("identifier_value",)
    readonly_fields = (
        "identifier_kind",
        "identifier_value",
        "purpose",
        "code_hash",
        "expires_at",
        "attempts",
        "created_at",
        "updated_at",
    )


@admin.register(AuthSession)
class AuthSessionAdmin(admin.ModelAdmin):
    """Read-oriented admin for tracked auth sessions/devices."""

    list_display = ("id", "user", "device_label", "ip_address", "is_revoked", "last_seen_at", "expires_at")
    list_filter = ("is_revoked", "device_label")
    search_fields = ("user__email", "user__phone_number", "refresh_jti", "ip_address", "user_agent")
    readonly_fields = [field.name for field in AuthSession._meta.fields]
    raw_id_fields = ("user", "revoked_by")
    ordering = ("-last_seen_at", "-created_at")

    def has_add_permission(self, request) -> bool:
        """Sessions are created by login services."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Session revocation must use audited APIs/services."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Session evidence should remain available for security review."""
        return False
