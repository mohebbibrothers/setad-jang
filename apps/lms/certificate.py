"""
Certificate utilities for LMS graduation.

Certificates in Ba'sat Mardom are both human-readable and machine-verifiable:
- a public verification code/slug is stored on the Certificate model
- the official Persian statement is generated from immutable snapshots
- a professional branded PDF is rendered with Pillow using the Ba'sat Mardom logo
"""

from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

from apps.authentication.choices import Gender
from apps.lms.choices import CertificateStatus
from apps.lms.models import Certificate

TEAL = (43, 119, 122)
GOLD = (247, 198, 103)
DARK = (37, 54, 60)
MUTED = (92, 108, 112)
LIGHT_BG = (253, 252, 248)
BORDER = (222, 186, 100)

A4_LANDSCAPE_PX = (3508, 2480)
LOGO_PATH = settings.BASE_DIR / "static" / "lms" / "certificates" / "basat_mardom_logo.jpg"
REGULAR_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
BOLD_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


class CertificateLike(Protocol):
    """Protocol for certificate-like objects accepted by rendering helpers."""

    gender_snapshot: str
    full_name_snapshot: str
    national_code_snapshot: str
    course_title_snapshot: str
    instructor_name_snapshot: str
    score_out_of_20: Decimal
    certificate_code: str
    verification_slug: str
    issued_at: object


def honorific_for_gender(gender: str) -> str:
    """Return Persian honorific based on profile gender snapshot."""
    if gender == Gender.FEMALE:
        return "خانم"
    if gender == Gender.MALE:
        return "آقای"
    return "جناب"


def build_certificate_text(certificate: CertificateLike) -> str:
    """Build the official Persian certificate text for display/PDF rendering."""
    honorific = honorific_for_gender(certificate.gender_snapshot)
    return (
        f"گواهی می‌شود {honorific} {certificate.full_name_snapshot} "
        f"به کد ملی {certificate.national_code_snapshot} با موفقیت دوره «{certificate.course_title_snapshot}» "
        "را در سامانه بعثت مردم گذرانده و "
        f"با نمره {certificate.score_out_of_20}/20 موفق به دریافت گواهی مهارت شده است. "
        f"کد اعتبارسنجی این گواهی: {certificate.certificate_code}"
    )


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    """Load a TrueType font with graceful fallback."""
    try:
        return ImageFont.truetype(str(path), size=size)
    except OSError:
        return ImageFont.truetype(str(REGULAR_FONT), size=size)


def _draw_centered_rtl(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int] = DARK,
) -> None:
    """Draw centered RTL-aware text using Pillow/raqm."""
    draw.text(xy, text, font=font, fill=fill, anchor="mm", direction="rtl", align="center")


def _draw_right_rtl(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int] = DARK,
) -> None:
    """Draw right-aligned RTL-aware text."""
    draw.text(xy, text, font=font, fill=fill, anchor="ra", direction="rtl", align="right")


def _paste_logo(canvas: Image.Image, *, logo_path: Path) -> None:
    """Paste Ba'sat Mardom logo on the certificate canvas."""
    if not logo_path.exists():
        return
    logo = Image.open(logo_path).convert("RGBA")
    logo.thumbnail((920, 380), Image.Resampling.LANCZOS)
    x = (canvas.width - logo.width) // 2
    canvas.alpha_composite(logo, (x, 135))


def render_certificate_image(
    certificate: CertificateLike,
    *,
    logo_path: Path = LOGO_PATH,
) -> Image.Image:
    """Render a professional certificate image ready for PDF export."""
    canvas = Image.new("RGBA", A4_LANDSCAPE_PX, (*LIGHT_BG, 255))
    draw = ImageDraw.Draw(canvas)
    width, height = canvas.size

    # Border and brand geometry.
    margin = 125
    draw.rounded_rectangle(
        (margin, margin, width - margin, height - margin),
        radius=42,
        outline=TEAL,
        width=10,
    )
    draw.rounded_rectangle(
        (margin + 35, margin + 35, width - margin - 35, height - margin - 35),
        radius=34,
        outline=BORDER,
        width=4,
    )
    draw.polygon([(0, height), (720, height), (0, height - 520)], fill=(*TEAL, 255))
    draw.polygon([(width, 0), (width - 640, 0), (width, 430)], fill=(*GOLD, 255))
    draw.ellipse((width - 485, 145, width - 245, 385), fill=(255, 255, 255, 110), outline=None)

    _paste_logo(canvas, logo_path=logo_path)

    title_font = _font(BOLD_FONT, 108)
    subtitle_font = _font(REGULAR_FONT, 46)
    body_font = _font(BOLD_FONT, 66)
    detail_font = _font(REGULAR_FONT, 42)
    small_font = _font(REGULAR_FONT, 34)
    code_font = _font(BOLD_FONT, 40)

    _draw_centered_rtl(draw, (width // 2, 625), "گواهی‌نامه پایان دوره", title_font, TEAL)
    _draw_centered_rtl(draw, (width // 2, 705), "سامانه آموزش بعثت مردم", subtitle_font, MUTED)

    honorific = honorific_for_gender(certificate.gender_snapshot)
    lines = [
        f"گواهی می‌شود {honorific} {certificate.full_name_snapshot}",
        f"به کد ملی {certificate.national_code_snapshot}",
        f"دوره «{certificate.course_title_snapshot}» را با موفقیت گذرانده است.",
        f"نمره نهایی: {certificate.score_out_of_20} از ۲۰",
    ]
    y = 920
    for line in lines:
        _draw_centered_rtl(draw, (width // 2, y), line, body_font if y == 920 else detail_font, DARK)
        y += 125

    _draw_centered_rtl(
        draw,
        (width // 2, 1515),
        f"مدرس دوره: {certificate.instructor_name_snapshot}",
        detail_font,
        TEAL,
    )
    _draw_centered_rtl(
        draw,
        (width // 2, 1610),
        "این گواهی به‌صورت الکترونیکی صادر شده و اصالت آن از طریق کد اعتبارسنجی زیر قابل بررسی است.",
        small_font,
        MUTED,
    )

    code_box = (width // 2 - 520, 1705, width // 2 + 520, 1845)
    draw.rounded_rectangle(code_box, radius=28, fill=(255, 255, 255, 255), outline=GOLD, width=5)
    _draw_centered_rtl(draw, (width // 2, 1750), "کد اعتبارسنجی", small_font, MUTED)
    _draw_centered_rtl(draw, (width // 2, 1810), certificate.certificate_code, code_font, TEAL)

    _draw_right_rtl(draw, (width - 260, height - 310), "مدیریت سامانه بعثت مردم", detail_font, DARK)
    _draw_right_rtl(draw, (width - 260, height - 245), "مرکز آموزش و توانمندسازی", small_font, MUTED)
    draw.line((width - 820, height - 360, width - 260, height - 360), fill=TEAL, width=4)

    _draw_right_rtl(
        draw,
        (width - 260, height - 155),
        f"شناسه عمومی اعتبارسنجی: {certificate.verification_slug}",
        small_font,
        MUTED,
    )
    return canvas.convert("RGB")


def build_certificate_pdf_bytes(certificate: CertificateLike) -> bytes:
    """Render and return a branded certificate PDF as bytes."""
    image = render_certificate_image(certificate)
    output = io.BytesIO()
    image.save(output, format="PDF", resolution=300.0)
    return output.getvalue()


def certificate_is_publicly_valid(certificate: Certificate) -> bool:
    """Return whether a certificate should verify as valid publicly."""
    return certificate.status == CertificateStatus.ISSUED and certificate.is_active


def normalize_certificate_score(score: Decimal) -> str:
    """Return score string for user-facing certificate displays."""
    return f"{score:.2f}"
