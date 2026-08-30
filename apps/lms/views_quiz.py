"""گروه دامنه‌ای `views_quiz` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.core.responses import CreatedResponse, ErrorResponse, SuccessResponse
from apps.lms import selectors, services
from apps.lms.permissions import IsLMSAdminUser
from apps.lms.serializers import (
    QuizAdminSerializer,
    QuizAttemptDetailSerializer,
    QuizAttemptSubmitSerializer,
    QuizCreateUpdateSerializer,
    QuizOptionAdminSerializer,
    QuizOptionCreateSerializer,
    QuizPublicSerializer,
    QuizQuestionAdminSerializer,
    QuizQuestionCreateSerializer,
    QuizUnlockCreateSerializer,
    QuizUnlockSerializer,
)
from apps.lms.services import (
    QuizAttemptLockedError,
    QuizAttemptSubmissionError,
    QuizNotAvailableError,
    QuizValidationError,
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


class LMSCourseQuizPublicView(APIView):
    """Return published quiz metadata for an enrolled course."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="lms_user_course_quiz_retrieve",
        tags=[TAG_LMS_USER],
        responses={200: QUIZ_PUBLIC_RESPONSE, 403: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, slug: str) -> SuccessResponse | ErrorResponse:
        """Return quiz metadata without correct answers."""
        course = selectors.get_public_course_by_slug(slug)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        quiz = selectors.get_published_quiz_for_course(course=course)
        if quiz is None:
            return ErrorResponse(
                message="برای این کلاس آزمونی منتشر نشده است.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return SuccessResponse(data=QuizPublicSerializer(quiz).data)


class LMSQuizAttemptStartView(APIView):
    """Start or resume a quiz attempt for an enrolled user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="lms_user_quiz_attempt_start",
        tags=[TAG_LMS_USER],
        request=None,
        responses={
            200: QUIZ_ATTEMPT_RESPONSE,
            201: QUIZ_ATTEMPT_RESPONSE,
            400: LMS_ERROR_RESPONSE,
            403: LMS_ERROR_RESPONSE,
            404: LMS_ERROR_RESPONSE,
        },
    )
    def post(
        self, request: Request, slug: str
    ) -> SuccessResponse | CreatedResponse | ErrorResponse:
        """Start a snapshot-based quiz attempt."""
        course = selectors.get_public_course_by_slug(slug)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        quiz = selectors.get_published_quiz_for_course(course=course)
        if quiz is None:
            return ErrorResponse(
                message="برای این کلاس آزمونی منتشر نشده است.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        try:
            attempt, created = services.start_quiz_attempt(quiz=quiz, user=request.user)
        except (QuizNotAvailableError, QuizAttemptLockedError, QuizValidationError) as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_403_FORBIDDEN)
        action = audit_actions.LMS_QUIZ_ATTEMPT_STARTED
        log_action_async(
            user_id=request.user.pk,
            action=action,
            resource_type="lms_quiz_attempt",
            resource_id=str(attempt.pk),
            extra_data={"quiz_id": quiz.pk, "course_id": course.pk},
            **extract_audit_metadata(request),
        )
        if created:
            return CreatedResponse(
                data=QuizAttemptDetailSerializer(attempt).data, message="آزمون برای شما آغاز شد."
            )
        return SuccessResponse(
            data=QuizAttemptDetailSerializer(attempt).data,
            message="تلاش در حال انجام قبلی شما بازیابی شد.",
        )


class LMSQuizAttemptDetailView(APIView):
    """Retrieve one owned quiz attempt."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="lms_user_quiz_attempt_retrieve",
        tags=[TAG_LMS_USER],
        responses={200: QUIZ_ATTEMPT_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, attempt_id: int) -> SuccessResponse | ErrorResponse:
        """Return attempt questions and submitted answers without leaking correct answers before pass."""
        attempt = selectors.get_quiz_attempt_by_id(user_id=request.user.pk, attempt_id=attempt_id)
        if attempt is None:
            return ErrorResponse(
                message="تلاش آزمون یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        return SuccessResponse(data=QuizAttemptDetailSerializer(attempt).data)


class LMSQuizAttemptSubmitView(APIView):
    """Submit answers for an in-progress quiz attempt."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="lms_user_quiz_attempt_submit",
        tags=[TAG_LMS_USER],
        request=QuizAttemptSubmitSerializer,
        responses={200: QUIZ_ATTEMPT_RESPONSE, 400: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def post(self, request: Request, attempt_id: int) -> SuccessResponse | ErrorResponse:
        """Submit attempt answers and calculate weighted score."""
        attempt = selectors.get_quiz_attempt_by_id(user_id=request.user.pk, attempt_id=attempt_id)
        if attempt is None:
            return ErrorResponse(
                message="تلاش آزمون یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        serializer = QuizAttemptSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            attempt = services.submit_quiz_attempt(
                attempt=attempt, answers=serializer.validated_data["answers"]
            )
        except QuizAttemptSubmissionError as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.LMS_QUIZ_ATTEMPT_SUBMITTED,
            resource_type="lms_quiz_attempt",
            resource_id=str(attempt.pk),
            extra_data={
                "score_out_of_20": str(attempt.score_out_of_20),
                "is_passed": attempt.is_passed,
            },
            **extract_audit_metadata(request),
        )
        log_action_async(
            user_id=request.user.pk,
            action=(
                audit_actions.LMS_QUIZ_ATTEMPT_PASSED
                if attempt.is_passed
                else audit_actions.LMS_QUIZ_ATTEMPT_FAILED
            ),
            resource_type="lms_quiz_attempt",
            resource_id=str(attempt.pk),
            extra_data={"quiz_id": attempt.quiz_id},
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=QuizAttemptDetailSerializer(attempt).data,
            message="پاسخ‌های آزمون با موفقیت ثبت شد.",
        )


class LMSAdminQuizDetailCreateView(APIView):
    """Admin create/retrieve quiz for a course."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_quiz_retrieve",
        tags=[TAG_LMS_ADMIN],
        responses={200: QUIZ_ADMIN_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, course_id: int) -> SuccessResponse | ErrorResponse:
        """Return quiz config for a course."""
        quiz = selectors.get_admin_quiz_by_course_id(course_id=course_id)
        if quiz is None:
            return ErrorResponse(
                message="آزمونی برای این کلاس یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        return SuccessResponse(data=QuizAdminSerializer(quiz).data)

    @extend_schema(
        operation_id="lms_admin_quiz_create_or_update",
        tags=[TAG_LMS_ADMIN],
        request=QuizCreateUpdateSerializer,
        responses={
            200: QUIZ_ADMIN_RESPONSE,
            201: QUIZ_ADMIN_RESPONSE,
            400: LMS_ERROR_RESPONSE,
            404: LMS_ERROR_RESPONSE,
        },
    )
    def post(
        self, request: Request, course_id: int
    ) -> SuccessResponse | CreatedResponse | ErrorResponse:
        """Create or update a draft quiz for a course."""
        course = selectors.get_admin_course_by_id(course_id)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = QuizCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quiz, created = services.create_or_update_quiz(course=course, **serializer.validated_data)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.LMS_QUIZ_CREATED,
            resource_type="lms_quiz",
            resource_id=str(quiz.pk),
            extra_data={"course_id": course.pk},
            **extract_audit_metadata(request),
        )
        if created:
            return CreatedResponse(
                data=QuizAdminSerializer(quiz).data, message="آزمون کلاس ساخته شد."
            )
        return SuccessResponse(
            data=QuizAdminSerializer(quiz).data, message="آزمون کلاس بروزرسانی شد."
        )


class LMSAdminQuizPublishView(APIView):
    """Admin publish quiz after validating questions/options."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_quiz_publish",
        tags=[TAG_LMS_ADMIN],
        request=None,
        responses={200: QUIZ_ADMIN_RESPONSE, 400: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def post(self, request: Request, course_id: int) -> SuccessResponse | ErrorResponse:
        """Publish quiz."""
        quiz = selectors.get_admin_quiz_by_course_id(course_id=course_id)
        if quiz is None:
            return ErrorResponse(message="آزمون یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            quiz = services.publish_quiz(quiz=quiz)
        except QuizValidationError as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.LMS_QUIZ_PUBLISHED,
            resource_type="lms_quiz",
            resource_id=str(quiz.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=QuizAdminSerializer(quiz).data, message="آزمون با موفقیت منتشر شد."
        )


class LMSAdminQuizQuestionCreateView(APIView):
    """Admin creates quiz questions. Users never create quiz questions."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_quiz_questions_create",
        tags=[TAG_LMS_ADMIN],
        request=QuizQuestionCreateSerializer,
        responses={201: QUIZ_QUESTION_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def post(self, request: Request, course_id: int) -> CreatedResponse | ErrorResponse:
        """Create quiz question."""
        quiz = selectors.get_admin_quiz_by_course_id(course_id=course_id)
        if quiz is None:
            return ErrorResponse(message="آزمون یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = QuizQuestionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = services.create_quiz_question(quiz=quiz, **serializer.validated_data)
        return CreatedResponse(
            data=QuizQuestionAdminSerializer(question).data, message="سؤال آزمون ساخته شد."
        )


class LMSAdminQuizOptionCreateView(APIView):
    """Admin creates answer options and marks the correct option."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_quiz_options_create",
        tags=[TAG_LMS_ADMIN],
        request=QuizOptionCreateSerializer,
        responses={201: QUIZ_OPTION_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def post(self, request: Request, question_id: int) -> CreatedResponse | ErrorResponse:
        """Create quiz option."""
        question = selectors.get_admin_quiz_question_by_id(question_id=question_id)
        if question is None:
            return ErrorResponse(
                message="سؤال آزمون یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        serializer = QuizOptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        option = services.create_quiz_option(question=question, **serializer.validated_data)
        return CreatedResponse(
            data=QuizOptionAdminSerializer(option).data, message="گزینه آزمون ساخته شد."
        )


class LMSAdminQuizUnlockView(APIView):
    """Admin manually unlocks extra attempts for a user."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_quiz_unlock",
        tags=[TAG_LMS_ADMIN],
        request=QuizUnlockCreateSerializer,
        responses={201: QUIZ_UNLOCK_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def post(self, request: Request, course_id: int) -> CreatedResponse | ErrorResponse:
        """Grant extra quiz attempts to a user."""
        quiz = selectors.get_admin_quiz_by_course_id(course_id=course_id)
        if quiz is None:
            return ErrorResponse(message="آزمون یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = QuizUnlockCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        User = get_user_model()
        user = User.objects.filter(pk=serializer.validated_data["user_id"]).first()
        if user is None:
            return ErrorResponse(message="کاربر یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        unlock = services.unlock_quiz_for_user(
            quiz=quiz,
            user=user,
            unlocked_by=request.user,
            reason=serializer.validated_data["reason"],
            extra_attempts=serializer.validated_data.get("extra_attempts", 1),
            valid_until=serializer.validated_data.get("valid_until"),
        )
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.LMS_QUIZ_UNLOCKED,
            resource_type="lms_quiz_unlock",
            resource_id=str(unlock.pk),
            extra_data={"quiz_id": quiz.pk, "user_id": user.pk},
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=QuizUnlockSerializer(unlock).data, message="آزمون برای کاربر بازگشایی شد."
        )
