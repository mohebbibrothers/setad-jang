"""
Full-pro matching engine for Kindness Wall.

The matcher connects opposite listing types using interpretable scoring. It is
language-aware for Persian text normalization, supports admin-managed synonyms,
and returns both a total score and a transparent breakdown for user/admin UX.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from django.utils import timezone

from apps.kindness_wall.choices import ListingType

PERSIAN_STOPWORDS = {
    "از",
    "به",
    "در",
    "و",
    "یا",
    "برای",
    "با",
    "که",
    "این",
    "آن",
    "من",
    "ما",
    "یک",
    "نیاز",
    "کمک",
    "دارم",
    "میخواهم",
    "می‌خواهم",
    "هستم",
    "دنبال",
}

DEFAULT_SYNONYMS = {
    "برنامه نویس": {"developer", "برنامهنویس", "توسعه دهنده", "طراح سایت"},
    "فول استک": {"fullstack", "full stack", "فولستک"},
    "سایت": {"وب", "website", "web"},
    "کار": {"شغل", "استخدام", "مشاغل"},
}


@dataclass(frozen=True)
class MatchScore:
    """Interpretable matching score result."""

    score: int
    breakdown: dict[str, int]
    reason_codes: list[str] = field(default_factory=list)
    explanation: str = ""


def normalize_text(value: str) -> str:
    """Normalize Persian/Arabic text for search and matching."""
    value = (value or "").strip().lower()
    replacements = {
        "ي": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "آ": "ا",
        "‌": " ",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = re.sub(r"[\u064B-\u065F\u0670]", "", value)
    value = re.sub(r"[^\w\s\u0600-\u06FF]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def tokenize(value: str, *, synonyms: dict[str, set[str]] | None = None) -> set[str]:
    """Tokenize normalized text and expand simple synonym groups."""
    normalized = normalize_text(value)
    tokens = {token for token in normalized.split() if token and token not in PERSIAN_STOPWORDS}
    synonym_map = synonyms or DEFAULT_SYNONYMS
    expanded = set(tokens)
    for keyword, aliases in synonym_map.items():
        keyword_norm = normalize_text(keyword)
        keyword_parts = set(keyword_norm.split())
        if keyword_norm in normalized or keyword_parts & tokens:
            expanded.update(normalize_text(alias) for alias in aliases)
            expanded.update(keyword_parts)
    return {token for token in expanded if token and token not in PERSIAN_STOPWORDS}


def jaccard_score(left: Iterable[str], right: Iterable[str], *, max_points: int) -> int:
    """Return Jaccard similarity scaled to max_points."""
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0
    return round((len(left_set & right_set) / len(left_set | right_set)) * max_points)


def calculate_match_score(*, source, target, synonyms: dict[str, set[str]] | None = None) -> MatchScore:
    """Calculate a 0..100 match score between opposite listing types."""
    if source.pk == target.pk or source.listing_type == target.listing_type:
        return MatchScore(score=0, breakdown={}, reason_codes=["same_type_or_self"], explanation="این آگهی قابل تطبیق نیست.")

    breakdown: dict[str, int] = {}
    reasons: list[str] = ["opposite_type"]
    breakdown["type_complementarity"] = 30

    breakdown["category_similarity"] = _category_score(source=source, target=target, reasons=reasons)
    breakdown["location_similarity"] = _location_score(source=source, target=target, reasons=reasons)

    source_title_tokens = tokenize(source.title, synonyms=synonyms)
    target_title_tokens = tokenize(target.title, synonyms=synonyms)
    source_desc_tokens = tokenize(source.description, synonyms=synonyms)
    target_desc_tokens = tokenize(target.description, synonyms=synonyms)
    breakdown["title_similarity"] = jaccard_score(source_title_tokens, target_title_tokens, max_points=20)
    breakdown["description_similarity"] = jaccard_score(source_desc_tokens, target_desc_tokens, max_points=10)
    if breakdown["title_similarity"]:
        reasons.append("title_overlap")
    if breakdown["description_similarity"]:
        reasons.append("description_overlap")

    source_tags = set(source.listing_tags.select_related("tag").values_list("tag__normalized_name", flat=True)) if getattr(source, "pk", None) else set()
    target_tags = set(target.listing_tags.select_related("tag").values_list("tag__normalized_name", flat=True)) if getattr(target, "pk", None) else set()
    breakdown["tag_similarity"] = jaccard_score(source_tags, target_tags, max_points=15)
    if breakdown["tag_similarity"]:
        reasons.append("tag_overlap")

    breakdown["freshness"] = _freshness_score(target=target)
    breakdown["profile_trust"] = 5 if getattr(target.owner, "is_phone_verified", False) else 0
    if breakdown["profile_trust"]:
        reasons.append("verified_phone")

    score = min(sum(breakdown.values()), 100)
    explanation = _build_explanation(score=score, reasons=reasons)
    return MatchScore(score=score, breakdown=breakdown, reason_codes=reasons, explanation=explanation)


def opposite_listing_type(listing_type: str) -> str:
    """Return the complementary fixed listing type."""
    return ListingType.OFFER_HELP if listing_type == ListingType.NEED_HELP else ListingType.NEED_HELP


def _category_score(*, source, target, reasons: list[str]) -> int:
    """Calculate tree-aware category score."""
    if source.category_id == target.category_id:
        reasons.append("same_category")
        return 25
    if source.category.parent_id and source.category.parent_id == target.category.parent_id:
        reasons.append("same_parent_category")
        return 18
    source_root = source.category.path.strip("/").split("/")[0] if source.category.path else ""
    target_root = target.category.path.strip("/").split("/")[0] if target.category.path else ""
    if source_root and source_root == target_root:
        reasons.append("same_root_category")
        return 12
    return 0


def _location_score(*, source, target, reasons: list[str]) -> int:
    """Calculate location score based on geo distance, city and province."""
    distance_km = _distance_km(source=source, target=target)
    if distance_km is not None:
        if distance_km <= 5:
            reasons.append("nearby_5km")
            return 20
        if distance_km <= 25:
            reasons.append("nearby_25km")
            return 16
        if distance_km <= 75:
            reasons.append("nearby_75km")
            return 10
    if source.city and target.city and normalize_text(source.city) == normalize_text(target.city):
        reasons.append("same_city")
        return 15
    if source.province and target.province and normalize_text(source.province) == normalize_text(target.province):
        reasons.append("same_province")
        return 8
    if not source.city or not target.city:
        return 2
    return 0


def _distance_km(*, source, target) -> float | None:
    """Return haversine distance in kilometers when both listings have coordinates."""
    if None in {source.latitude, source.longitude, target.latitude, target.longitude}:
        return None
    lat1, lon1, lat2, lon2 = map(float, [source.latitude, source.longitude, target.latitude, target.longitude])
    radius_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _freshness_score(*, target) -> int:
    """Calculate freshness score for target listing."""
    reference = target.published_at or target.created_at
    if not reference:
        return 0
    age_days = max((timezone.now() - reference).days, 0)
    if age_days <= 3:
        return 5
    if age_days <= 14:
        return 3
    if age_days <= 30:
        return 1
    return 0


def _build_explanation(*, score: int, reasons: list[str]) -> str:
    """Build human-readable Persian match explanation."""
    labels = {
        "opposite_type": "نوع آگهی‌ها مکمل هم هستند",
        "same_category": "دسته‌بندی دقیقاً یکسان است",
        "same_parent_category": "زیرمجموعه یک دسته والد هستند",
        "same_root_category": "در یک شاخه اصلی قرار دارند",
        "nearby_5km": "فاصله مکانی بسیار نزدیک است",
        "nearby_25km": "فاصله مکانی نزدیک است",
        "nearby_75km": "در محدوده مکانی قابل قبول قرار دارند",
        "same_city": "شهر مشترک است",
        "same_province": "استان مشترک است",
        "title_overlap": "عنوان‌ها کلیدواژه‌های مشترک دارند",
        "description_overlap": "توضیحات آگهی‌ها مشابه است",
        "tag_overlap": "تگ‌های مشترک دارند",
        "verified_phone": "شماره تماس کمک‌کننده/درخواست‌کننده تأیید شده است",
    }
    parts = [labels[reason] for reason in reasons if reason in labels]
    strength = "بسیار بالا" if score >= 80 else "بالا" if score >= 60 else "متوسط" if score >= 40 else "ضعیف"
    return f"میزان تطابق {strength} است: " + "، ".join(parts)
