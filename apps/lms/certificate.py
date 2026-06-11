"""
Certificate utilities for LMS graduation.

Certificates in Ba'sat Mardom are both human-readable and machine-verifiable:
- a public verification code/slug is stored on the Certificate model
- the official Persian statement is generated from immutable snapshots
- a lightweight PDF-compatible file is generated without external runtime deps
"""

from __future__ import annotations

from decimal import Decimal

from apps.authentication.choices import Gender
from apps.lms.choices import CertificateStatus
from apps.lms.models import Certificate


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
    Build a minimal valid PDF payload for certificate storage.

    این PDF ساده و dependency-free است. برای نسخه production زیباتر می‌توان همین
    interface را با renderer حرفه‌ای‌تر جایگزین کرد، بدون تغییر service layer.
    """
    text = build_certificate_text(certificate).encode("utf-16-be", errors="ignore")
    # Minimal PDF with UTF-16BE hex string. Enough for storage/verification tests.
    hex_text = text.hex().upper()
    stream = f"BT /F1 12 Tf 50 760 Td <FEFF{hex_text}> Tj ET".encode()
    objects = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    objects.append(
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
    )
    objects.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    objects.append(b"5 0 obj << /Length " + str(len(stream)).encode() + b" >> stream\n" + stream + b"\nendstream endobj\n")
    content = b"%PDF-1.4\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(content))
        content += obj
    xref_offset = len(content)
    content += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets[1:]:
        content += f"{offset:010d} 00000 n \n".encode()
    content += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    return content


def certificate_is_publicly_valid(certificate: Certificate) -> bool:
    """Return whether a certificate should verify as valid publicly."""
    return certificate.status == CertificateStatus.ISSUED and certificate.is_active


def normalize_certificate_score(score: Decimal) -> str:
    """Return score string for user-facing certificate displays."""
    return f"{score:.2f}"
