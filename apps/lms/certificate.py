"""
Certificate utilities for LMS graduation.

Certificates in Ba'sat Mardom are both human-readable and machine-verifiable:
- a public verification code/slug is stored on the Certificate model
- the official Persian statement is generated from immutable snapshots
- a polished PDF is generated with the official Ba'sat Mardom logo

The PDF renderer intentionally uses Pillow, which is already a project dependency.
This keeps certificate generation deterministic and deployable without adding a
new native PDF dependency. The rendering API is isolated here so a future HTML/PDF
renderer can replace it without touching service-layer logic.
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from pathlib import Path
from textwrap import wrap

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

from apps.authentication.choices import Gender
from apps.lms.choices import CertificateStatus
from apps.lms.models import Certificate

_TEAL = (39, 122, 126)
_GOLD = (245, 198, 108)
_DARK = (35, 55, 60)
_MUTED = (100, 115, 120)
_BG = (251, 252, 250)
_WHITE = (255, 255, 255)

_A4_LANDSCAPE = (1754, 1240)
_FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_LOGO_PATH = Path(settings.BASE_DIR) / "static" / "lms" / "certificates" / "basat_mardom_logo.jpg"


def honorific_for_gender(gender: str) -> str:
    """Return Persian honorific based on profile gender snapshot."""
    if gender == Gender.FEMALE:
        return "خانم"
    if gender == Gender.MALE:
        return "آقای"
    return "جناب"


def build_certificate_text(certificate: Certificate) -> str:
    """Build the official Persian certificate text for display/PDF rendering."""
    honorific = honorific_for_gender(certificate.gender_snapshot)
    return (
        f"گواهی می‌شود {honorific} {certificate.full_name_snapshot} "
        f"به کد ملی {certificate.national_code_snapshot} با موفقیت دوره «{certificate.course_title_snapshot}» "
        "را در سامانه بعثت مردم گذرانده و "
        f"با نمره {certificate.score_out_of_20}/20 موفق به دریافت گواهی مهارت شده است. "
        f"کد اعتبارسنجی این گواهی: {certificate.certificate_code}"
    )


def build_certificate_pdf_bytes(certificate: Certificate) -> bytes:
    """
    Build a polished one-page PDF certificate using the official logo.

    The output is a proper PDF generated from a high-resolution image canvas. It
    includes a decorative border, the uploaded Ba'sat Mardom logo, official
    Persian certificate text, score, verification code, and issue date.
    """
    canvas = Image.new("RGB", _A4_LANDSCAPE, _BG)
    draw = ImageDraw.Draw(canvas)
    width, height = canvas.size

    _draw_background(draw, width, height)
    _draw_logo(canvas)
    _draw_certificate_text(draw, certificate, width, height)

    buffer = BytesIO()
    canvas.save(buffer, format="PDF", resolution=150.0)
    return buffer.getvalue()


def normalize_certificate_score(score: Decimal) -> str:
    """Return score string for user-facing certificate displays."""
    return f"{score:.2f}"


def certificate_is_publicly_valid(certificate: Certificate) -> bool:
    """Return whether a certificate should verify as valid publicly."""
    return certificate.status == CertificateStatus.ISSUED and certificate.is_active


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a Persian-capable font."""
    return ImageFont.truetype(_FONT_BOLD if bold else _FONT_REGULAR, size=size)


def _draw_background(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    """Draw border, ornaments, and watermark-safe certificate background."""
    margin = 70
    draw.rounded_rectangle(
        [margin, margin, width - margin, height - margin],
        radius=34,
        fill=_WHITE,
        outline=_TEAL,
        width=8,
    )
    draw.rounded_rectangle(
        [margin + 24, margin + 24, width - margin - 24, height - margin - 24],
        radius=24,
        outline=_GOLD,
        width=4,
    )

    # Decorative top/bottom ribbons.
    draw.rectangle([margin, margin, width - margin, margin + 26], fill=_TEAL)
    draw.rectangle([margin, height - margin - 26, width - margin, height - margin], fill=_TEAL)
    draw.ellipse([width - 360, 120, width - 120, 360], fill=(250, 231, 190), outline=_GOLD, width=4)
    draw.ellipse(
        [120, height - 360, 330, height - 150], fill=(232, 246, 246), outline=_TEAL, width=3
    )


def _draw_logo(canvas: Image.Image) -> None:
    """Place the official logo on the certificate if available."""
    if not _LOGO_PATH.exists():
        return
    logo = Image.open(_LOGO_PATH).convert("RGB")
    max_w, max_h = 520, 190
    logo.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    x = (canvas.width - logo.width) // 2
    y = 110
    canvas.paste(logo, (x, y))


def _draw_certificate_text(
    draw: ImageDraw.ImageDraw, certificate: Certificate, width: int, height: int
) -> None:
    """Draw all certificate text using RTL-aware rendering."""
    title_font = _font(64, bold=True)
    subtitle_font = _font(34, bold=True)
    body_font = _font(34)
    label_font = _font(28, bold=True)
    small_font = _font(24)

    _text(draw, (width // 2, 345), "گواهی‌نامه پایان دوره", title_font, fill=_TEAL, anchor="mm")
    _text(draw, (width // 2, 405), "سامانه بعثت مردم", subtitle_font, fill=_GOLD, anchor="mm")

    body = build_certificate_text(certificate)
    lines = _wrap_rtl(body, width_chars=78)
    y = 520
    for line in lines:
        _text(draw, (width // 2, y), line, body_font, fill=_DARK, anchor="mm")
        y += 58

    score_text = f"نمره نهایی: {normalize_certificate_score(certificate.score_out_of_20)} از ۲۰"
    code_text = f"کد اعتبارسنجی: {certificate.certificate_code}"
    issue_text = f"تاریخ صدور: {certificate.issued_at:%Y-%m-%d}"

    info_y = height - 320
    draw.rounded_rectangle(
        [230, info_y - 40, width - 230, info_y + 160],
        radius=20,
        fill=(248, 250, 250),
        outline=(220, 230, 230),
        width=2,
    )
    _text(draw, (width - 300, info_y), score_text, label_font, fill=_TEAL, anchor="ra")
    _text(draw, (width - 300, info_y + 56), code_text, label_font, fill=_DARK, anchor="ra")
    _text(draw, (width - 300, info_y + 112), issue_text, small_font, fill=_MUTED, anchor="ra")

    _text(draw, (310, height - 170), "مهر و امضای سامانه", small_font, fill=_MUTED, anchor="mm")
    draw.line([210, height - 215, 410, height - 215], fill=_TEAL, width=3)


def _text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    *,
    fill: tuple[int, int, int],
    anchor: str,
) -> None:
    """Draw Persian/RTL text with libraqm when available."""
    draw.text(xy, text, font=font, fill=fill, anchor=anchor, direction="rtl", language="fa")


def _wrap_rtl(text: str, *, width_chars: int) -> list[str]:
    """Wrap Persian text by words for centered certificate body."""
    return wrap(text, width=width_chars, break_long_words=False, replace_whitespace=False)
