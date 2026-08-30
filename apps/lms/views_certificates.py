"""گروه دامنه‌ای `views_certificates` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.core.pagination import StandardPagination
from apps.core.responses import ErrorResponse, SuccessResponse
from apps.lms import selectors
from apps.lms.permissions import IsLMSAdminUser
from apps.lms.serializers import (
    CertificateRevokeSerializer,
    CertificateSerializer,
    CertificateVerifySerializer,
)
from apps.lms.services import (
    revoke_certificate,
)
from apps.lms.throttles import (
    LMSCertificateVerifyThrottle,
)

from .views_common import (  # noqa: F401 — re-exportِ رایگان برای بدنه‌های منتقل‌شده
    ANSWER_RESPONSE,
    CATEGORY_LIST_RESPONSE,
    CATEGORY_RESPONSE,
    CERTIFICATE_LIST_RESPONSE,
    CERTIFICATE_RESPONSE,
    CERTIFICATE_VERIFY_RESPONSE,
    COURSE_ANALYTICS_RESPONSE,
    COURSE_LEADERBOARD_RESPONSE,
    COURSE_LIST_RESPONSE,
    COURSE_REPORT_RESPONSE,
    COURSE_RESPONSE,
    DISCUSSION_REPORT_LIST_RESPONSE,
    DISCUSSION_REPORT_RESPONSE,
    ENROLLMENT_DETAIL_RESPONSE,
    ENROLLMENT_LIST_RESPONSE,
    ENROLLMENT_RESPONSE,
    LEARNING_RECOMMENDATION_OVERVIEW_RESPONSE,
    LEARNING_RECOMMENDATION_RESPONSE,
    LEARNING_STATEMENT_LIST_RESPONSE,
    LESSON_LIST_RESPONSE,
    LESSON_MEDIA_RESPONSE,
    LESSON_PROGRESS_RESPONSE,
    LESSON_RESPONSE,
    LMS_ERROR_RESPONSE,
    QUESTION_LIST_RESPONSE,
    QUESTION_RESPONSE,
    QUIZ_ADMIN_RESPONSE,
    QUIZ_ATTEMPT_RESPONSE,
    QUIZ_OPTION_RESPONSE,
    QUIZ_PUBLIC_RESPONSE,
    QUIZ_QUESTION_RESPONSE,
    QUIZ_UNLOCK_RESPONSE,
    SKILL_LIST_RESPONSE,
    TAG_LMS_ADMIN,
    TAG_LMS_PUBLIC,
    TAG_LMS_USER,
    VIDEO_PROCESSING_JOB_RESPONSE,
)


class LMSUserCertificateListView(APIView):
    """List certificates owned by the current user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="lms_user_certificates_list",
        tags=[TAG_LMS_USER],
        responses={200: CERTIFICATE_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """Return paginated user certificates."""
        queryset = selectors.get_user_certificates(user_id=request.user.pk)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = CertificateSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(
            serializer.data, message="لیست مدارک شما دریافت شد."
        )


class LMSUserCertificateDetailView(APIView):
    """Retrieve one certificate owned by the current user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="lms_user_certificates_retrieve",
        tags=[TAG_LMS_USER],
        responses={200: CERTIFICATE_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, certificate_id: int) -> SuccessResponse | ErrorResponse:
        """Return one owned certificate."""
        certificate = selectors.get_user_certificate_by_id(
            user_id=request.user.pk,
            certificate_id=certificate_id,
        )
        if certificate is None:
            return ErrorResponse(
                message="مدرکی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        return SuccessResponse(
            data=CertificateSerializer(certificate, context={"request": request}).data
        )


class LMSCertificateVerifyView(APIView):
    """Public certificate verification endpoint."""

    permission_classes = [AllowAny]
    # یافتهٔ ممیزی ۵.۱: اوراکل شمارش گواهی — throttle اختصاصی per-IP.
    throttle_classes = [LMSCertificateVerifyThrottle]

    @extend_schema(
        operation_id="lms_public_certificates_verify",
        tags=[TAG_LMS_PUBLIC],
        responses={200: CERTIFICATE_VERIFY_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, verification_slug: str) -> SuccessResponse | ErrorResponse:
        """Verify certificate validity publicly."""
        certificate = selectors.get_certificate_by_verification_slug(
            verification_slug=verification_slug
        )
        if certificate is None or certificate.status != "issued" or not certificate.is_active:
            return ErrorResponse(
                message="مدرک معتبر یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        return SuccessResponse(
            data=CertificateVerifySerializer(certificate, context={"request": request}).data,
            message="اعتبار مدرک با موفقیت تأیید شد.",
        )


class LMSAdminCertificateRevokeView(APIView):
    """Admin endpoint for revoking a certificate."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_certificates_revoke",
        tags=[TAG_LMS_ADMIN],
        request=CertificateRevokeSerializer,
        responses={200: CERTIFICATE_RESPONSE, 400: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def post(self, request: Request, certificate_id: int) -> SuccessResponse | ErrorResponse:
        """Revoke one certificate and derived skill."""
        certificate = selectors.get_admin_certificate_by_id(certificate_id=certificate_id)
        if certificate is None:
            return ErrorResponse(message="مدرک یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = CertificateRevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        certificate = revoke_certificate(
            certificate=certificate,
            revoked_by=request.user,
            reason=serializer.validated_data["reason"],
        )
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.LMS_CERTIFICATE_REVOKED,
            resource_type="lms_certificate",
            resource_id=str(certificate.pk),
            extra_data={"course_id": certificate.course_id, "user_id": certificate.user_id},
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=CertificateSerializer(certificate, context={"request": request}).data,
            message="مدرک با موفقیت باطل شد.",
        )
