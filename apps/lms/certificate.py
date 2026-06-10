"""
Certificate utilities for LMS graduation.

The first implementation stores certificate data in the database and keeps the PDF
field ready for generated files. PDF rendering is implemented in the certificate
phase to keep Phase 1 focused on domain foundations.
"""

from __future__ import annotations

from apps.lms.models import Certificate

CERTIFICATE_TEXT_TEMPLATE = (
    "گواهی می‌شود {full_name} به کد ملی {national_code} با موفقیت دوره «{course_title}» "
    "را در سامانه بعثت مردم گذرانده و با نمره {score}/20 موفق به دریافت گواهی مهارت شده است."
)


def build_certificate_text(certificate: Certificate) -> str:
    """Build the official Persian certificate text for display/PDF rendering."""
    return CERTIFICATE_TEXT_TEMPLATE.format(
        full_name=certificate.full_name_snapshot,
        national_code=certificate.national_code_snapshot,
        course_title=certificate.course_title_snapshot,
        score=certificate.score_out_of_20,
    )
