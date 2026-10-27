"""گیت‌های معماری/سیاست دیوار مهربانی v2 — ممیزی منبع (source-level).

این تست‌ها جلوی رگرسیون ساختاری را می‌گیرند: بازگشت fan-out اعلان، ورود
نویسنده از API عمومی، افشای تماس در فهرست، taskِ stub، یا حذف audit.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APP = REPO_ROOT / "apps" / "kindness_wall"
SOURCE_APPS = REPO_ROOT / "apps"


def _read(relpath: str) -> str:
    """خواندن متن یک فایل منبع اپ (نسبی به ریشهٔ ریپو)."""
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


def _app_source(name: str) -> str:
    """متن یک ماژول اپ دیوار مهربانی."""
    return _read(f"apps/kindness_wall/{name}")


def test_every_kindness_view_is_guarded() -> None:
    """هر view ادمین باید permission صریح داشته باشد؛ هیچ view عمومی نوشتن باز ندارد."""
    for fname in ("views.py", "views_admin.py"):
        src = _app_source(fname)
        for block in re.findall(r"class Kindness\w+\(APIView\):(.*?)(?=\nclass |\Z)", src, re.S):
            assert "permission_classes" in block, f"{fname}: class بدون permission_classes"


def test_no_notifications_fanout_returns() -> None:
    """v2 اعلان درون‌اپی ندارد؛ import/call notify در services/views ممنوع."""
    for fname in ("services.py", "views.py", "views_admin.py", "signals.py"):
        src = _app_source(fname)
        assert "notify_kindness" not in src, f"اعلان بازیگشت در {fname}"


def test_offer_is_the_only_user_write_path() -> None:
    """کاربر فقط offer می‌سازد؛ هیچ مسیر create برای listing/report/bookmark نیست."""
    src = _app_source("views.py")
    assert "def post" in src  # offer-create
    for forbidden in ("KindnessListingCreateView", "ReportCreateView", "BookmarkView"):
        assert forbidden not in src, f"مسیر نوشتن کاربری قدیمی {forbidden} برگشته"
    urls = _app_source("urls.py")
    assert "reveal" not in urls.lower()
    assert "bookmark" not in urls.lower()
    assert "report/" not in urls.lower()


def test_contact_never_in_list_payload() -> None:
    """سریالایزر فهرست نباید هیچ فیلد contact_ را داشته باشد."""
    src = _app_source("serializers.py")
    list_class = re.search(
        r"class KindnessListingListSerializer\(.*?\n(.*?)\nclass ", src, re.S
    ).group(1)
    assert "contact_phone" not in list_class
    assert "channel_payload" not in list_class


def test_admin_model_registration_complete() -> None:
    """چهار مدل = چهار ModelAdmin ثبت‌شده (و images پنهان از ایندکس)."""
    admin_src = _app_source("admin.py")
    for model in (
        "KindnessCategory",
        "KindnessListing",
        "KindnessOffer",
        "KindnessListingImage",
    ):
        assert f"@admin.register({model})" in admin_src, f"{model} ثبت نشده"
    assert "HiddenFromAdminIndexMixin" in admin_src


def test_listing_admin_wires_all_lifecycle_actions() -> None:
    """اکشن‌های چرخه حیات کامل باید در ListingAdmin باشند."""
    admin_src = _app_source("admin.py")
    for action in (
        "publish_listings",
        "renew_listings",
        "fulfill_listings",
        "archive_listings",
        "export_listings_xlsx",
    ):
        assert action in admin_src, f"اکشن {action} گم شده"


def test_images_inline_caps_and_orders() -> None:
    """inline تصاویر باید max_num از ثابت choices بخورد (نه عدد جادویی)."""
    admin_src = _app_source("admin.py")
    assert "max_num = MAX_IMAGES_PER_LISTING" in admin_src


def test_export_uses_streaming_workbook_only() -> None:
    """export نباید openpyxl Workbook را مستقیم import/سازد؛ باید stream کند."""
    src = _app_source("export.py")
    assert "Workbook()" not in src, "Workbook مستقیم یعنی بار کامل حافظه"
    assert "StreamingExcelSheet" in src


def test_cache_invalidation_registered() -> None:
    """signals باید register_public_cache_invalidation را با models کامل صدا بزند."""
    src = _app_source("signals.py")
    assert "register_public_cache_invalidation" in src
    assert "KindnessOffer" in src  # شمارندهٔ offer روی کش فهرست اثر دارد


def test_apps_ready_imports_signals() -> None:
    """signals باید در ready() import شود وگرنه invalidation هرگز وصل نمی‌شود."""
    src = _app_source("apps.py")
    assert "def ready" in src
    assert re.search(r"def ready\(self\).*?import signals", src, re.S), (
        "signals در ready import نشده"
    )


def test_throttle_scope_declared_and_used() -> None:
    """اسکوپ offer_create هم در throttle class و هم در view استفاده شده."""
    th = _app_source("throttles.py")
    views = _app_source("views.py")
    assert 'scope = "kindness_offer_create"' in th
    assert "KindnessOfferCreateThrottle" in views


def test_search_fts_migration_present() -> None:
    """ایندکس‌های v2 باید با همان نام‌های قرارداد ساخته شوند (نگهبان تست PG)."""
    src = _read("apps/kindness_wall/migrations/0005_search_indexes_v2.py")
    assert "kindness_wall_kindnesslisting_search_fts_idx" in src
    assert 'connection.vendor != "postgresql"' in src


def test_legacy_shims_kept_for_old_migrations() -> None:
    """توابع upload/validator قدیمی باید بمانند وگرنه import مهاجرت ۰۰۰ می‌شکند."""
    models_src = _app_source("models.py")
    validators_src = _app_source("validators.py")
    assert "def category_cover_upload_path" in models_src
    assert "def listing_image_upload_path" in models_src
    assert "def validate_match_score" in validators_src


def test_rebuild_drops_every_v1_model() -> None:
    """مهاجرت بازسازی باید هر ۱۲ مدل v1 را حذف کند تا جدولی یتیم نماند."""
    src = _read("apps/kindness_wall/migrations/0004_v2_rebuild.py")
    for name in (
        "KindnessTag",
        "KindnessKeywordAlias",
        "KindnessContactReveal",
        "KindnessBookmark",
        "KindnessListingReport",
        "KindnessMatch",
        "KindnessListingTag",
        "KindnessListingImage",
        "KindnessRiskSignal",
        "KindnessDuplicateCandidate",
        "KindnessListing",
        "KindnessCategory",
    ):
        assert f"name='{name}'," in src, f"حذف {name} از مهاجرت جا افتاده"
    # مدل‌های تازهٔ v2 هم باید ساخته شوند
    for name in ("KindnessCategory", "KindnessListing", "KindnessListingImage", "KindnessOffer"):
        assert f"CreateModel(\n            name='{name}'" in src


def test_command_center_counts_only_public_board() -> None:
    """خلاصهٔ command_center نباید به مدل‌های حذف‌شدهٔ v1 اشاره کند."""
    src = _read("apps/command_center/selectors.py")
    for gone in ("KindnessContactReveal", "KindnessRiskSignal", "KindnessMatch"):
        assert gone not in src


def test_admin_i18n_labels_persian_only() -> None:
    """برچسب‌های ادمین نباید واژهٔ انگلیسی Kindness داشته باشند و باید ۴ مدل باشند."""
    src = _read("apps/core/admin_i18n.py")
    block = src[src.index("# Kindness wall") : src.index("# LMS")]
    assert "Kindness" not in re.sub(r"#[^\n]*", "", block), "برچسب انگلیسی در رجیستری مانده"
    for model in ("kindnesscategory", "kindnesslisting", "kindnesslistingimage", "kindnessoffer"):
        assert f'"{model}"' in block, f"برچسب {model} نیست"
    # هیچ مدل v1 نباید در رجیستری بماند
    for gone in ("kindnesstag", "kindnessmatch", "kindnessbookmark", "kindnessrisksignal"):
        assert gone not in src


def test_audit_actions_cover_lifecycle() -> None:
    """اکشن‌های audit جدید باید در registry تعریف و در admin استفاده شده باشند."""
    actions = _read("apps/audit_logs/actions.py")
    for const in (
        "KINDNESS_LISTING_PUBLISHED",
        "KINDNESS_LISTING_FULFILLED",
        "KINDNESS_LISTING_RENEWED",
        "KINDNESS_OFFER_REVIEWED",
        "KINDNESS_LISTINGS_EXPORTED",
    ):
        assert const in actions, f"اکشن {const} تعریف نشده"
    admin_src = _app_source("admin.py")
    for const in ("KINDNESS_LISTING_CREATED", "KINDNESS_CATEGORY_UPDATED"):
        assert const in admin_src


def test_no_orphan_kindness_models_referenced_elsewhere() -> None:
    """هیچ اپ/تستی نباید هنوز مدل‌های حذف‌شدهٔ kindness را import کند."""
    gone = re.compile(
        r"from apps\.kindness_wall\.models import .*(?:"
        r"KindnessContactReveal|KindnessMatch|KindnessBookmark|KindnessRiskSignal"
        r"|KindnessDuplicateCandidate|KindnessListingTag|KindnessListingReport|KindnessTag"
        r"|KindnessKeywordAlias)"
    )
    offenders: list[str] = []
    for path in sorted((SOURCE_APPS.parent / "apps").rglob("*.py")) + sorted(
        (SOURCE_APPS.parent / "tests").rglob("*.py")
    ):
        if "/migrations/" in path.as_posix() or "__pycache__" in path.as_posix():
            continue
        if gone.search(path.read_text(encoding="utf-8")):
            offenders.append(path.as_posix())
    assert offenders == [], "ارجاع به مدل حذف‌شده:\n" + "\n".join(offenders)
