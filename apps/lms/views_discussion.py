"""گروه دامنه‌ای `views_discussion` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.core.pagination import StandardPagination
from apps.core.responses import CreatedResponse, ErrorResponse, SuccessResponse
from apps.lms import selectors, services
from apps.lms.permissions import IsLMSAdminUser
from apps.lms.serializers import (
    DiscussionModerationSerializer,
    DiscussionReportCreateSerializer,
    DiscussionReportReviewSerializer,
    DiscussionReportSerializer,
    LessonAnswerCreateSerializer,
    LessonAnswerSerializer,
    LessonQuestionCreateSerializer,
    LessonQuestionSerializer,
)
from apps.lms.services import (
    LMSDiscussionAccessError,
    LMSDiscussionModerationError,
)
from apps.lms.throttles import (
    LMSDiscussionThrottle,
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


class LMSLessonQuestionListCreateView(APIView):
    """List questions for a lesson and allow enrolled users to ask immediately."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [LMSDiscussionThrottle]

    @extend_schema(
        operation_id="lms_lesson_questions_list",
        tags=[TAG_LMS_USER],
        responses={200: QUESTION_LIST_RESPONSE, 403: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, lesson_id: int) -> Response:
        """Return lesson questions for enrolled users."""
        lesson = selectors.get_lesson_for_progress(lesson_id=lesson_id)
        if lesson is None:
            return ErrorResponse(message="جلسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            services.ensure_user_enrolled_for_lesson(user=request.user, lesson=lesson)
        except LMSDiscussionAccessError as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_403_FORBIDDEN)
        queryset = selectors.get_lesson_questions(lesson_id=lesson.pk)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = LessonQuestionSerializer(page, many=True)
        return paginator.get_paginated_response(
            serializer.data, message="پرسش‌های جلسه با موفقیت دریافت شد."
        )

    @extend_schema(
        operation_id="lms_lesson_questions_create",
        tags=[TAG_LMS_USER],
        request=LessonQuestionCreateSerializer,
        responses={
            201: QUESTION_RESPONSE,
            400: LMS_ERROR_RESPONSE,
            403: LMS_ERROR_RESPONSE,
            404: LMS_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, lesson_id: int) -> CreatedResponse | ErrorResponse:
        """Create a visible question under a lesson."""
        lesson = selectors.get_lesson_for_progress(lesson_id=lesson_id)
        if lesson is None:
            return ErrorResponse(message="جلسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = LessonQuestionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            question = services.create_lesson_question(
                lesson=lesson,
                user=request.user,
                title=serializer.validated_data["title"],
                body=serializer.validated_data["body"],
            )
        except LMSDiscussionAccessError as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.LMS_QUESTION_CREATED,
            resource_type="lms_lesson_question",
            resource_id=str(question.pk),
            extra_data={"lesson_id": lesson.pk, "course_id": lesson.course_id},
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=LessonQuestionSerializer(question).data, message="سؤال شما با موفقیت ثبت شد."
        )


class LMSQuestionAnswerCreateView(APIView):
    """Create answer for a lesson question."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [LMSDiscussionThrottle]

    @extend_schema(
        operation_id="lms_question_answers_create",
        tags=[TAG_LMS_USER],
        request=LessonAnswerCreateSerializer,
        responses={
            201: ANSWER_RESPONSE,
            400: LMS_ERROR_RESPONSE,
            403: LMS_ERROR_RESPONSE,
            404: LMS_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, question_id: int) -> CreatedResponse | ErrorResponse:
        """Create an answer under an existing question."""
        question = selectors.get_lesson_question_by_id(question_id=question_id)
        if question is None:
            return ErrorResponse(message="سؤال یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = LessonAnswerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            answer = services.create_lesson_answer(
                question=question,
                user=request.user,
                body=serializer.validated_data["body"],
                is_instructor_answer=bool(request.user.is_staff or request.user.is_superuser),
            )
        except LMSDiscussionAccessError as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.LMS_ANSWER_CREATED,
            resource_type="lms_lesson_answer",
            resource_id=str(answer.pk),
            extra_data={"question_id": question.pk},
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=LessonAnswerSerializer(answer).data, message="پاسخ با موفقیت ثبت شد."
        )


class LMSQuestionAcceptAnswerView(APIView):
    """Accept an answer for a question by owner or admin."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="lms_question_answers_accept",
        tags=[TAG_LMS_USER],
        request=None,
        responses={200: ANSWER_RESPONSE, 403: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def post(
        self, request: Request, question_id: int, answer_id: int
    ) -> SuccessResponse | ErrorResponse:
        """Mark answer as accepted."""
        question = selectors.get_lesson_question_by_id(question_id=question_id)
        answer = selectors.get_lesson_answer_by_id(answer_id=answer_id)
        if question is None or answer is None:
            return ErrorResponse(
                message="سؤال یا پاسخ یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        try:
            answer = services.accept_lesson_answer(
                question=question, answer=answer, user=request.user
            )
        except (LMSDiscussionAccessError, LMSDiscussionModerationError) as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_403_FORBIDDEN)
        return SuccessResponse(
            data=LessonAnswerSerializer(answer).data, message="پاسخ به‌عنوان پاسخ پذیرفته‌شده ثبت شد."
        )


class LMSQuestionReportView(APIView):
    """Report a lesson question for moderation."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [LMSDiscussionThrottle]

    @extend_schema(
        operation_id="lms_questions_report",
        tags=[TAG_LMS_USER],
        request=DiscussionReportCreateSerializer,
        responses={
            201: DISCUSSION_REPORT_RESPONSE,
            403: LMS_ERROR_RESPONSE,
            404: LMS_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, question_id: int) -> CreatedResponse | ErrorResponse:
        """Report a question."""
        question = selectors.get_lesson_question_by_id(question_id=question_id)
        if question is None:
            return ErrorResponse(message="سؤال یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = DiscussionReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            report = services.report_lesson_question(
                question=question, reported_by=request.user, **serializer.validated_data
            )
        except LMSDiscussionAccessError as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.LMS_DISCUSSION_REPORTED,
            resource_type="lms_discussion_report",
            resource_id=str(report.pk),
            extra_data={"question_id": question.pk},
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=DiscussionReportSerializer(report).data,
            message="گزارش شما ثبت شد و توسط ادمین بررسی می‌شود.",
        )


class LMSAnswerReportView(APIView):
    """Report a lesson answer for moderation."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [LMSDiscussionThrottle]

    @extend_schema(
        operation_id="lms_answers_report",
        tags=[TAG_LMS_USER],
        request=DiscussionReportCreateSerializer,
        responses={
            201: DISCUSSION_REPORT_RESPONSE,
            403: LMS_ERROR_RESPONSE,
            404: LMS_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, answer_id: int) -> CreatedResponse | ErrorResponse:
        """Report an answer."""
        answer = selectors.get_lesson_answer_by_id(answer_id=answer_id)
        if answer is None:
            return ErrorResponse(message="پاسخ یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = DiscussionReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            report = services.report_lesson_answer(
                answer=answer, reported_by=request.user, **serializer.validated_data
            )
        except LMSDiscussionAccessError as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.LMS_DISCUSSION_REPORTED,
            resource_type="lms_discussion_report",
            resource_id=str(report.pk),
            extra_data={"answer_id": answer.pk},
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=DiscussionReportSerializer(report).data,
            message="گزارش شما ثبت شد و توسط ادمین بررسی می‌شود.",
        )


class LMSAdminQuestionModerationView(APIView):
    """Admin moderation for questions."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_questions_moderate",
        tags=[TAG_LMS_ADMIN],
        request=DiscussionModerationSerializer,
        responses={200: QUESTION_RESPONSE, 400: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def patch(self, request: Request, question_id: int) -> SuccessResponse | ErrorResponse:
        """Moderate one question."""
        question = selectors.get_lesson_question_by_id(question_id=question_id)
        if question is None:
            return ErrorResponse(message="سؤال یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = DiscussionModerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = services.moderate_lesson_question(
            question=question,
            status=serializer.validated_data["status"],
            is_pinned=serializer.validated_data.get("is_pinned"),
        )
        return SuccessResponse(
            data=LessonQuestionSerializer(question).data, message="وضعیت سؤال بروزرسانی شد."
        )


class LMSAdminAnswerModerationView(APIView):
    """Admin moderation for answers."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_answers_moderate",
        tags=[TAG_LMS_ADMIN],
        request=DiscussionModerationSerializer,
        responses={200: ANSWER_RESPONSE, 400: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def patch(self, request: Request, answer_id: int) -> SuccessResponse | ErrorResponse:
        """Moderate one answer."""
        answer = selectors.get_lesson_answer_by_id(answer_id=answer_id)
        if answer is None:
            return ErrorResponse(message="پاسخ یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = DiscussionModerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        answer = services.moderate_lesson_answer(
            answer=answer,
            status=serializer.validated_data["status"],
            is_accepted=serializer.validated_data.get("is_accepted"),
        )
        return SuccessResponse(
            data=LessonAnswerSerializer(answer).data, message="وضعیت پاسخ بروزرسانی شد."
        )


class LMSAdminDiscussionReportListView(APIView):
    """Admin list of discussion reports."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_discussion_reports_list",
        tags=[TAG_LMS_ADMIN],
        responses={200: DISCUSSION_REPORT_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """Return paginated discussion reports."""
        queryset = selectors.get_admin_discussion_reports()
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = DiscussionReportSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class LMSAdminDiscussionReportReviewView(APIView):
    """Admin review for a discussion report."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_discussion_reports_review",
        tags=[TAG_LMS_ADMIN],
        request=DiscussionReportReviewSerializer,
        responses={
            200: DISCUSSION_REPORT_RESPONSE,
            400: LMS_ERROR_RESPONSE,
            404: LMS_ERROR_RESPONSE,
        },
    )
    def patch(self, request: Request, report_id: int) -> SuccessResponse | ErrorResponse:
        """Review one discussion report."""
        report = selectors.get_admin_discussion_report_by_id(report_id=report_id)
        if report is None:
            return ErrorResponse(message="گزارش یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = DiscussionReportReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = services.review_discussion_report(
            report=report, reviewed_by=request.user, status=serializer.validated_data["status"]
        )
        return SuccessResponse(
            data=DiscussionReportSerializer(report).data, message="گزارش گفتگو بررسی شد."
        )
