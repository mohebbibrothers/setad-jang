"""
Database models for Kindness Wall (Divar-e Mehrabani).

The domain connects people who need help with people who want to help. It is not a
marketplace and no financial transaction happens inside the system. The model set
is intentionally full-pro from the start: tree categories, moderation workflow,
images, tags, synonym aliases, matching, duplicate detection, contact reveal
tracking, reports, bookmarks, expiration, and analytics-friendly counters.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import BaseModel
from apps.kindness_wall.choices import (
    DuplicateStatus,
    ListingImageKind,
    ListingStatus,
    ListingType,
    MatchStatus,
    ReportReason,
    ReportStatus,
    RiskSeverity,
    RiskSignalType,
    RiskStatus,
    TagSource,
)
from apps.kindness_wall.managers import (
    KindnessCategoryAllManager,
    KindnessCategoryManager,
    KindnessListingAllManager,
    KindnessListingManager,
)
from apps.kindness_wall.validators import (
    validate_listing_image_extension,
    validate_listing_image_size,
    validate_match_score,
)


def category_cover_upload_path(instance: KindnessCategory, filename: str) -> str:
    """Build upload path for category covers."""
    return f"kindness_wall/categories/{instance.pk or 'new'}/cover/{filename}"


def listing_image_upload_path(instance: KindnessListingImage, filename: str) -> str:
    """Build upload path for listing images."""
    return f"kindness_wall/listings/{instance.listing_id}/images/{filename}"


def _unique_slug(
    *, model: type[models.Model], value: str, max_length: int, exclude_pk: int | None = None
) -> str:
    """Generate collision-safe unicode slug for a model."""
    base = slugify(value, allow_unicode=True)[:max_length] or uuid.uuid4().hex[:12]
    candidate = base
    suffix = 2
    manager = getattr(model, "all_objects", model.objects)
    while manager.filter(slug=candidate).exclude(pk=exclude_pk).exists():
        suffix_text = f"-{suffix}"
        candidate = f"{base[: max_length - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate


class KindnessCategory(BaseModel):
    """Admin-managed tree category for Kindness Wall listings."""

    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="دسته والد",
    )
    title = models.CharField(max_length=180, verbose_name="عنوان دسته")
    slug = models.SlugField(max_length=220, unique=True, allow_unicode=True, blank=True)
    description = models.TextField(blank=True, verbose_name="توضیحات")
    icon = models.CharField(max_length=80, blank=True, verbose_name="آیکن")
    cover_image = models.ImageField(
        upload_to=category_cover_upload_path,
        blank=True,
        null=True,
        verbose_name="تصویر کاور",
    )
    path = models.CharField(max_length=600, unique=True, blank=True, db_index=True)
    depth = models.PositiveSmallIntegerField(default=0)
    order = models.PositiveIntegerField(default=0)
    listings_count = models.PositiveIntegerField(default=0)
    published_listings_count = models.PositiveIntegerField(default=0)

    objects = KindnessCategoryManager()
    all_objects = KindnessCategoryAllManager()

    class Meta:
        verbose_name = "دسته‌بندی دیوار مهربانی"
        verbose_name_plural = "دسته‌بندی‌های دیوار مهربانی"
        ordering = ["depth", "order", "title"]
        indexes = [
            models.Index(fields=["parent", "is_active", "order"]),
            models.Index(fields=["path"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "title"], name="uniq_kindness_category_parent_title"
            ),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Generate slug/path/depth consistently for tree categories."""
        if not self.slug:
            self.slug = _unique_slug(
                model=KindnessCategory, value=self.title, max_length=220, exclude_pk=self.pk
            )
        if self.parent_id:
            parent = self.parent
            self.depth = parent.depth + 1
            self.path = f"{parent.path.rstrip('/')}/{self.slug}/"
        else:
            self.depth = 0
            self.path = f"/{self.slug}/"
        super().save(*args, **kwargs)


class KindnessTag(BaseModel):
    """Global normalized tag dictionary used by search and matching."""

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=160, unique=True, allow_unicode=True, blank=True)
    normalized_name = models.CharField(max_length=160, unique=True, db_index=True)
    usage_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "تگ دیوار مهربانی"
        verbose_name_plural = "تگ‌های دیوار مهربانی"
        ordering = ["normalized_name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Generate slug and normalized name."""
        from apps.kindness_wall.matching import normalize_text

        if not self.normalized_name:
            self.normalized_name = normalize_text(self.name)
        if not self.slug:
            self.slug = _unique_slug(
                model=KindnessTag, value=self.normalized_name, max_length=160, exclude_pk=self.pk
            )
        super().save(*args, **kwargs)


class KindnessKeywordAlias(BaseModel):
    """Admin-managed synonym dictionary for smarter Persian matching."""

    keyword = models.CharField(max_length=120)
    alias = models.CharField(max_length=120)
    normalized_keyword = models.CharField(max_length=160, db_index=True)
    normalized_alias = models.CharField(max_length=160, db_index=True)

    class Meta:
        verbose_name = "هم‌معنی جستجوی دیوار مهربانی"
        verbose_name_plural = "هم‌معنی‌های جستجوی دیوار مهربانی"
        constraints = [
            models.UniqueConstraint(
                fields=["normalized_keyword", "normalized_alias"],
                name="uniq_kindness_keyword_alias",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.keyword} = {self.alias}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Normalize keyword/alias for matching."""
        from apps.kindness_wall.matching import normalize_text

        self.normalized_keyword = normalize_text(self.keyword)
        self.normalized_alias = normalize_text(self.alias)
        super().save(*args, **kwargs)


class KindnessListing(BaseModel):
    """Main listing connecting a need with a helper or vice versa."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="kindness_listings"
    )
    listing_type = models.CharField(max_length=20, choices=ListingType.choices, db_index=True)
    category = models.ForeignKey(
        KindnessCategory, on_delete=models.PROTECT, related_name="listings"
    )
    title = models.CharField(max_length=260)
    slug = models.SlugField(max_length=320, unique=True, allow_unicode=True, blank=True)
    description = models.TextField()
    province = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    district = models.CharField(max_length=120, blank=True)
    address_hint = models.CharField(max_length=260, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    contact_phone_snapshot = models.CharField(max_length=30)
    owner_full_name_snapshot = models.CharField(max_length=260)
    owner_avatar_snapshot = models.CharField(max_length=512, blank=True)
    owner_gender_snapshot = models.CharField(max_length=20, blank=True)
    owner_province_snapshot = models.CharField(max_length=100, blank=True)
    owner_city_snapshot = models.CharField(max_length=100, blank=True)

    status = models.CharField(
        max_length=30, choices=ListingStatus.choices, default=ListingStatus.DRAFT, db_index=True
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kindness_reviewed_listings",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    suspension_reason = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    view_count = models.PositiveIntegerField(default=0)
    contact_reveal_count = models.PositiveIntegerField(default=0)
    bookmark_count = models.PositiveIntegerField(default=0)
    report_count = models.PositiveIntegerField(default=0)
    match_generation_version = models.PositiveIntegerField(default=1)
    last_matched_at = models.DateTimeField(null=True, blank=True)
    search_document = models.TextField(blank=True, default="")

    objects = KindnessListingManager()
    all_objects = KindnessListingAllManager()

    class Meta:
        verbose_name = "آگهی دیوار مهربانی"
        verbose_name_plural = "آگهی‌های دیوار مهربانی"
        ordering = ["-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "listing_type", "-published_at"]),
            models.Index(fields=["category", "status", "-published_at"]),
            models.Index(fields=["province", "city", "status"]),
            models.Index(fields=["owner", "status", "-created_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_listing_type_display()} — {self.title}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Generate slug and search document."""
        if not self.slug:
            self.slug = _unique_slug(
                model=KindnessListing, value=self.title, max_length=320, exclude_pk=self.pk
            )
        self.search_document = (
            f"{self.title} {self.description} {self.province} {self.city} {self.category.title}"
        )
        super().save(*args, **kwargs)

    @property
    def is_public(self) -> bool:
        """Return whether listing is visible publicly."""
        if self.status != ListingStatus.PUBLISHED or not self.is_active:
            return False
        return self.expires_at is None or self.expires_at > timezone.now()


class KindnessListingImage(BaseModel):
    """Image attached to a listing with cover/gallery semantics."""

    listing = models.ForeignKey(KindnessListing, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(
        upload_to=listing_image_upload_path,
        validators=[validate_listing_image_extension, validate_listing_image_size],
    )
    caption = models.CharField(max_length=260, blank=True)
    alt_text = models.CharField(max_length=260, blank=True)
    image_kind = models.CharField(
        max_length=20, choices=ListingImageKind.choices, default=ListingImageKind.GALLERY
    )
    is_cover = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    file_size = models.PositiveIntegerField(default=0)
    blur_hash = models.CharField(max_length=120, blank=True)

    class Meta:
        verbose_name = "تصویر آگهی دیوار مهربانی"
        verbose_name_plural = "تصاویر آگهی دیوار مهربانی"
        ordering = ["order", "id"]
        indexes = [models.Index(fields=["listing", "is_cover", "order"])]
        constraints = [
            models.UniqueConstraint(
                fields=["listing"],
                condition=models.Q(is_cover=True),
                name="uniq_kindness_listing_cover_image",
            )
        ]


class KindnessListingTag(BaseModel):
    """Weighted tag assigned to a listing."""

    listing = models.ForeignKey(
        KindnessListing, on_delete=models.CASCADE, related_name="listing_tags"
    )
    tag = models.ForeignKey(KindnessTag, on_delete=models.PROTECT, related_name="listing_tags")
    weight = models.PositiveSmallIntegerField(default=1)
    source = models.CharField(max_length=30, choices=TagSource.choices, default=TagSource.MANUAL)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["listing", "tag"], name="uniq_kindness_listing_tag")
        ]
        indexes = [
            models.Index(fields=["tag", "weight"]),
            models.Index(fields=["listing", "source"]),
        ]


class KindnessMatch(BaseModel):
    """Materialized smart match between opposite listing types."""

    source_listing = models.ForeignKey(
        KindnessListing, on_delete=models.CASCADE, related_name="outgoing_matches"
    )
    target_listing = models.ForeignKey(
        KindnessListing, on_delete=models.CASCADE, related_name="incoming_matches"
    )
    score = models.PositiveSmallIntegerField(validators=[validate_match_score])
    score_breakdown = models.JSONField(default=dict, blank=True)
    reason_codes = models.JSONField(default=list, blank=True)
    explanation = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=MatchStatus.choices, default=MatchStatus.ACTIVE, db_index=True
    )
    algorithm_version = models.PositiveIntegerField(default=1)
    generated_at = models.DateTimeField(default=timezone.now)
    dismissed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    dismissed_at = models.DateTimeField(null=True, blank=True)
    contacted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_listing", "target_listing"], name="uniq_kindness_match_pair"
            ),
            models.CheckConstraint(
                name="kindness_match_not_self",
                condition=~models.Q(source_listing=models.F("target_listing")),
            ),
        ]
        indexes = [
            models.Index(fields=["source_listing", "status", "-score"]),
            models.Index(fields=["target_listing", "status", "-score"]),
        ]


class KindnessContactReveal(BaseModel):
    """Audit/safety record for revealing a listing owner's phone number."""

    listing = models.ForeignKey(
        KindnessListing, on_delete=models.PROTECT, related_name="contact_reveals"
    )
    viewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="kindness_contact_reveals"
    )
    listing_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="kindness_received_contact_reveals",
    )
    phone_snapshot = models.CharField(max_length=30)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    request_id = models.CharField(max_length=80, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["listing", "-created_at"]),
            models.Index(fields=["viewer", "-created_at"]),
        ]


class KindnessListingReport(BaseModel):
    """User report against a listing for admin moderation."""

    listing = models.ForeignKey(KindnessListing, on_delete=models.CASCADE, related_name="reports")
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="kindness_reports"
    )
    reason = models.CharField(max_length=40, choices=ReportReason.choices)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=ReportStatus.choices, default=ReportStatus.PENDING
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kindness_reviewed_reports",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["listing", "status"]),
        ]


class KindnessBookmark(BaseModel):
    """User bookmark for a published listing."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="kindness_bookmarks"
    )
    listing = models.ForeignKey(KindnessListing, on_delete=models.CASCADE, related_name="bookmarks")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "listing"], name="uniq_kindness_bookmark")
        ]
        indexes = [models.Index(fields=["user", "-created_at"])]


class KindnessRiskSignal(BaseModel):
    """Safety/risk signal generated from suspicious Kindness Wall behavior."""

    signal_type = models.CharField(max_length=40, choices=RiskSignalType.choices, db_index=True)
    severity = models.CharField(
        max_length=20, choices=RiskSeverity.choices, default=RiskSeverity.MEDIUM, db_index=True
    )
    status = models.CharField(
        max_length=20, choices=RiskStatus.choices, default=RiskStatus.OPEN, db_index=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="kindness_risk_signals",
    )
    listing = models.ForeignKey(
        KindnessListing,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="risk_signals",
    )
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kindness_reviewed_risk_signals",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "سیگنال ریسک دیوار مهربانی"
        verbose_name_plural = "سیگنال‌های ریسک دیوار مهربانی"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["signal_type", "status", "-created_at"]),
            models.Index(fields=["user", "status", "-created_at"]),
            models.Index(fields=["listing", "status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.signal_type}:{self.severity}:{self.status}"


class KindnessDuplicateCandidate(BaseModel):
    """Potential duplicate listing relation surfaced to admins during review."""

    listing = models.ForeignKey(
        KindnessListing, on_delete=models.CASCADE, related_name="duplicate_candidates"
    )
    candidate_listing = models.ForeignKey(
        KindnessListing, on_delete=models.CASCADE, related_name="duplicate_of_candidates"
    )
    score = models.PositiveSmallIntegerField(validators=[validate_match_score])
    reason = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=DuplicateStatus.choices, default=DuplicateStatus.ACTIVE
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["listing", "candidate_listing"], name="uniq_kindness_duplicate_candidate"
            ),
            models.CheckConstraint(
                name="kindness_duplicate_not_self",
                condition=~models.Q(listing=models.F("candidate_listing")),
            ),
        ]
        indexes = [models.Index(fields=["listing", "status", "-score"])]
