"""
Views اپ تبیین — API endpoints برای محتوای جهاد تبیین.

ساختار:
- Public: بدون نیاز به لاگین (با cache هوشمند سطح selector)
- Admin: فقط برای ادمین‌ها (بدون cache برای دیدن state واقعی)
- Admin async sync: اجرای دستی sync به‌صورت غیرهمزمان توسط Celery
  + endpoint جداگانه برای پیگیری وضعیت task

اصول طراحی:
- View هیچ business logic مستقیمی ندارد و فقط orchestration می‌کند.
- View هیچ‌گاه با Celery یا AsyncResult مستقیماً کار نمی‌کند؛
  هرچه نیاز است از طریق service layer گرفته می‌شود.
- response envelope و استانداردهای Swagger پروژه به‌طور کامل رعایت می‌شوند.
- Audit log فقط برای endpointهای mutating (toggle, sync dispatch) ثبت می‌شود.
"""

from __future__ import annotations

import hashlib
import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.reverse import reverse
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.authentication.permissions import IsAdminUser
from apps.core.pagination import StandardPagination
from apps.core.responses import ErrorResponse, SuccessResponse
from apps.core.schemas import (
    build_error_response_serializer,
    build_paginated_success_response_serializer,
    build_success_response_serializer,
)
from apps.tabyin import selectors, services
from apps.tabyin.filters import (
    AdminTabyinContentFilter,
    PublicTabyinContentFilter,
)
from apps.tabyin.serializers import (
    AdminSyncTaskDispatchedSerializer,
    AdminSyncTaskStatusSerializer,
    AdminSyncTriggerSerializer,
    AdminTabyinContentDetailSerializer,
    AdminTabyinContentListSerializer,
    AdminTabyinContentToggleSerializer,
    AdminTabyinSubmissionQueueSerializer,
    AdminTabyinSubmissionReviewSerializer,
    PublicTabyinContentDetailSerializer,
    PublicTabyinContentListSerializer,
    TabyinMediaUploadInputSerializer,
    TabyinMediaUploadResultSerializer,
    TabyinUploadConfigSerializer,
    UserTabyinSubmissionCreateSerializer,
    UserTabyinSubmissionDetailSerializer,
    UserTabyinSubmissionListSerializer,
)
from apps.tabyin.throttles import (
    TabyinPublicAnonThrottle,
    TabyinPublicUserThrottle,
    TabyinSyncThrottle,
    TabyinUploadThrottle,
)
from apps.tabyin.uploading import get_upload_config_payload

logger = logging.getLogger("apps.tabyin")


# ============================================================
# Tag Constants — استاندارد یکپارچه پروژه
# ============================================================

TAG_TABYIN_PUBLIC = "تبیین — عمومی"
TAG_TABYIN_ADMIN = "تبیین — مدیریت"


# ============================================================
# Helpers
# ============================================================


def _build_filters_signature(request: Request) -> str:
    """
    ساخت یک امضای یکتا و کوتاه از فیلترهای اعمال‌شده روی درخواست.

    این امضا در ساخت cache key استفاده می‌شود تا درخواست‌های با
    فیلترهای متفاوت، cache جداگانه داشته باشند.
    """
    relevant_keys = sorted(k for k in request.query_params.keys() if k not in {"page", "page_size"})
    if not relevant_keys:
        return "no_filters"

    parts = [f"{k}={request.query_params.get(k, '')}" for k in relevant_keys]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ============================================================
# Public Views
# ============================================================


@extend_schema_view(
    get=extend_schema(
        operation_id="tabyin_public_contents_list",
        summary="لیست محتواهای جهاد تبیین",
        description=(
            "لیست محتواهای عمومی — پاسخ paginated و قابل فیلتر.\n\n"
            "**فیلترهای موجود:**\n"
            "- `media_type`: image / video / audio\n"
            "- `author`: جستجو در نام نویسنده\n"
            "- `search`: جستجو در عنوان و توضیحات\n\n"
            "این endpoint با cache سطح selector بهینه شده است "
            "(TTL=۶۰ ثانیه، invalidation خودکار پس از sync یا تغییرات ادمین)."
        ),
        tags=[TAG_TABYIN_PUBLIC],
        responses={
            200: build_paginated_success_response_serializer(
                name="PublicTabyinContentListResponse",
                item_serializer=PublicTabyinContentListSerializer,
            ),
        },
    )
)
class PublicTabyinContentListView(APIView):
    """لیست محتواهای جهاد تبیین — عمومی (با cache هوشمند)."""

    permission_classes = [AllowAny]
    throttle_classes = [TabyinPublicAnonThrottle, TabyinPublicUserThrottle]

    def get(self, request: Request) -> SuccessResponse:
        filters_signature = _build_filters_signature(request)
        page_number = request.query_params.get("page", "1")
        page_size = request.query_params.get(
            "page_size",
            str(StandardPagination.page_size),
        )

        cached_payload = selectors.get_public_contents_page_cached(
            page=page_number,
            page_size=page_size,
            filters_signature=filters_signature,
        )
        if cached_payload is not None:
            logger.debug("Serving public list from cache")
            return SuccessResponse(data=cached_payload)

        queryset = selectors.get_public_contents()

        filterset = PublicTabyinContentFilter(
            data=request.query_params,
            queryset=queryset,
        )
        if filterset.is_valid():
            queryset = filterset.qs

        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = PublicTabyinContentListSerializer(page, many=True)

        response = paginator.get_paginated_response(serializer.data)

        selectors.set_public_contents_page_cache(
            page=page_number,
            page_size=page_size,
            filters_signature=filters_signature,
            payload=response.data["data"],
        )

        return response


@extend_schema_view(
    get=extend_schema(
        operation_id="tabyin_public_content_retrieve",
        summary="جزئیات محتوای تبیین",
        description=(
            "جزئیات یک محتوا با external_id.\n\n"
            "این endpoint با cache سطح selector بهینه شده است "
            "(TTL=۵ دقیقه، invalidation خودکار پس از sync یا تغییرات ادمین)."
        ),
        tags=[TAG_TABYIN_PUBLIC],
        responses={
            200: build_success_response_serializer(
                name="PublicTabyinContentDetailResponse",
                data_serializer=PublicTabyinContentDetailSerializer,
            ),
            404: build_error_response_serializer(
                name="PublicTabyinContentDetailNotFoundResponse",
            ),
        },
    )
)
class PublicTabyinContentDetailView(APIView):
    """جزئیات یک محتوای تبیین — عمومی (با cache هوشمند)."""

    permission_classes = [AllowAny]
    throttle_classes = [TabyinPublicAnonThrottle, TabyinPublicUserThrottle]

    def get(
        self,
        request: Request,
        external_id: str,
    ) -> SuccessResponse | ErrorResponse:
        content = selectors.get_public_content_detail_cached(external_id)
        if content is None:
            return ErrorResponse(
                message="محتوا یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = PublicTabyinContentDetailSerializer(content)
        return SuccessResponse(data=serializer.data)


# ============================================================
# User Views — Content submissions
# ============================================================


class UserTabyinSubmissionListCreateView(APIView):
    """Authenticated users can submit content and list their own submissions."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="tabyin_user_submissions_list",
        summary="لیست محتواهای ارسالی من",
        tags=[TAG_TABYIN_PUBLIC],
        responses={
            200: build_paginated_success_response_serializer(
                name="UserTabyinSubmissionListResponse",
                item_serializer=UserTabyinSubmissionListSerializer,
            ),
        },
    )
    def get(self, request: Request) -> SuccessResponse:
        queryset = selectors.get_user_submissions(user_id=request.user.pk)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = UserTabyinSubmissionListSerializer(page, many=True)
        return paginator.get_paginated_response(
            serializer.data,
            message="لیست محتواهای ارسالی شما با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="tabyin_user_submission_create",
        summary="ارسال محتوای جدید برای بررسی ادمین",
        tags=[TAG_TABYIN_PUBLIC],
        request=UserTabyinSubmissionCreateSerializer,
        responses={
            201: build_success_response_serializer(
                name="UserTabyinSubmissionCreatedResponse",
                data_serializer=UserTabyinSubmissionDetailSerializer,
            ),
            400: build_error_response_serializer(name="UserTabyinSubmissionCreateBadRequest"),
        },
    )
    def post(self, request: Request) -> SuccessResponse:
        serializer = UserTabyinSubmissionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        content = services.submit_user_content(
            user=request.user,
            title=serializer.validated_data["title"],
            description=serializer.validated_data["description"],
            attachments=serializer.validated_data.get("attachments", []),
        )

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.TABYIN_USER_SUBMISSION_SUBMITTED,
            resource_type="tabyin_content",
            resource_id=str(content.pk),
            extra_data={"external_id": content.external_id},
            **metadata,
        )

        return SuccessResponse(
            data=UserTabyinSubmissionDetailSerializer(content).data,
            status_code=status.HTTP_201_CREATED,
            message="محتوای شما ثبت شد و پس از تأیید ادمین نمایش داده می‌شود.",
        )


class UserTabyinSubmissionDetailView(APIView):
    """Authenticated users can inspect one of their own submissions."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="tabyin_user_submission_retrieve",
        summary="جزئیات محتوای ارسالی من",
        tags=[TAG_TABYIN_PUBLIC],
        responses={
            200: build_success_response_serializer(
                name="UserTabyinSubmissionDetailResponse",
                data_serializer=UserTabyinSubmissionDetailSerializer,
            ),
            404: build_error_response_serializer(name="UserTabyinSubmissionNotFound"),
        },
    )
    def get(self, request: Request, content_id: int) -> SuccessResponse | ErrorResponse:
        content = selectors.get_user_submission_by_id(
            user_id=request.user.pk,
            content_id=content_id,
        )
        if content is None:
            return ErrorResponse(
                message="محتوایی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return SuccessResponse(data=UserTabyinSubmissionDetailSerializer(content).data)


class UserTabyinMediaUploadView(APIView):
    """
    آپلود مستقیمِ رسانه برای روایت‌های مردمی (multipart).

    فایل بلافاصله روی استوریجِ عمومیِ خودمان ذخیره می‌شود و نشانیِ داخلی‌اش
    برمی‌گردد تا در همان گذر به‌عنوان url پیوستِ روایت ثبت شود — از همان
    لحظه، روایت دیگر به هیچ نشانیِ بیرونی بدهکار نیست. متادیتا (ابعاد،
    مدت، حجم) هم همان‌جا استخراج و برگردانده می‌شود تا استودیو همان را
    به کاربر نشان دهد.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [TabyinUploadThrottle]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        operation_id="tabyin_user_media_upload",
        summary="بارگذاری مستقیم رسانه برای روایت (تصویر/ویدئو/صوت/سایر)",
        tags=[TAG_TABYIN_PUBLIC],
        request=TabyinMediaUploadInputSerializer,
        responses={
            201: build_success_response_serializer(
                name="UserTabyinMediaUploadResponse",
                data_serializer=TabyinMediaUploadResultSerializer,
            ),
            400: build_error_response_serializer(name="UserTabyinMediaUploadBadRequest"),
        },
    )
    def post(self, request: Request) -> SuccessResponse | ErrorResponse:
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return ErrorResponse(
                message="فایلی ارسال نشده است؛ فایل را در فیلد file بفرست.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        try:
            stored = services.store_user_media_upload(
                user=request.user,
                uploaded_file=uploaded_file,
            )
        except DjangoValidationError as exc:
            return ErrorResponse(
                message="فایل پذیرفته نیست.",
                errors=getattr(exc, "message_dict", {"file": exc.messages}),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.TABYIN_USER_MEDIA_UPLOADED,
            resource_type="tabyin_media",
            resource_id=stored.name,
            extra_data={
                "media_type": stored.media_type,
                "size_bytes": stored.size_bytes,
                "original_name": stored.original_name,
            },
            **metadata,
        )

        return SuccessResponse(
            data=TabyinMediaUploadResultSerializer(stored).data,
            status_code=status.HTTP_201_CREATED,
            message="فایل روی سرور بعثت ذخیره شد؛ حالا می‌توانی آن را به روایتت پیوست کنی.",
        )


class TabyinUploadConfigView(APIView):
    """
    قرارداد عمومیِ آپلود — سقف حجم و فرمت‌های مجازِ هر نوع رسانه.

    استودیو این قرارداد را می‌خواند تا قوانینِ بک‌اند را دقیق و به‌روز
    به کاربر نشان دهد (و با مقدارِ داخلِ‌خودش هم fallback دارد).
    """

    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="tabyin_upload_config",
        summary="قرارداد آپلود رسانه — سقف حجم و فرمت‌های مجاز",
        tags=[TAG_TABYIN_PUBLIC],
        responses={
            200: build_success_response_serializer(
                name="TabyinUploadConfigResponse",
                data_serializer=TabyinUploadConfigSerializer,
            ),
        },
    )
    def get(self, request: Request) -> SuccessResponse:
        del request  # بدون استفاده — قرارداد ثابت است
        return SuccessResponse(
            data=TabyinUploadConfigSerializer(get_upload_config_payload()).data,
            message="قرارداد آپلود رسانه دریافت شد.",
        )


# ============================================================
# Admin Views — Content
# ============================================================


@extend_schema_view(
    get=extend_schema(
        operation_id="tabyin_admin_contents_list",
        summary="لیست محتواها — ادمین",
        description=(
            "لیست تمام محتواها شامل غیرفعال و حذف‌شده — paginated و قابل فیلتر.\n\n"
            "**فیلترهای موجود:**\n"
            "- `media_type`: image / video / audio\n"
            "- `author`: جستجو در نام نویسنده\n"
            "- `is_active`: فیلتر فعال/غیرفعال\n"
            "- `is_deleted_in_source`: فیلتر حذف‌شده در منبع\n"
            "- `search`: جستجو در عنوان و توضیحات\n\n"
            "این endpoint cache نمی‌شود — همیشه آخرین state را برمی‌گرداند."
        ),
        tags=[TAG_TABYIN_ADMIN],
        responses={
            200: build_paginated_success_response_serializer(
                name="AdminTabyinContentListResponse",
                item_serializer=AdminTabyinContentListSerializer,
            ),
            403: build_error_response_serializer(
                name="AdminTabyinContentListForbiddenResponse",
            ),
        },
    )
)
class AdminTabyinContentListView(APIView):
    """لیست تمام محتواها — ادمین (بدون cache برای داده live)."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request: Request) -> SuccessResponse:
        queryset = selectors.get_admin_contents()

        filterset = AdminTabyinContentFilter(
            data=request.query_params,
            queryset=queryset,
        )
        if filterset.is_valid():
            queryset = filterset.qs

        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request)

        serializer = AdminTabyinContentListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


@extend_schema_view(
    get=extend_schema(
        operation_id="tabyin_admin_content_retrieve",
        summary="جزئیات محتوا — ادمین",
        description=(
            "جزئیات کامل یک محتوا شامل `raw_payload` (داده خام JSON منبع).\n\n"
            "این endpoint cache نمی‌شود — همیشه آخرین state را برمی‌گرداند."
        ),
        tags=[TAG_TABYIN_ADMIN],
        responses={
            200: build_success_response_serializer(
                name="AdminTabyinContentDetailResponse",
                data_serializer=AdminTabyinContentDetailSerializer,
            ),
            403: build_error_response_serializer(
                name="AdminTabyinContentDetailForbiddenResponse",
            ),
            404: build_error_response_serializer(
                name="AdminTabyinContentDetailNotFoundResponse",
            ),
        },
    ),
)
class AdminTabyinContentDetailView(APIView):
    """جزئیات محتوا — ادمین."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(
        self,
        request: Request,
        external_id: str,
    ) -> SuccessResponse | ErrorResponse:
        content = selectors.get_admin_content_by_external_id(external_id)
        if content is None:
            return ErrorResponse(
                message="محتوا یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = AdminTabyinContentDetailSerializer(content)
        return SuccessResponse(data=serializer.data)


@extend_schema_view(
    patch=extend_schema(
        operation_id="tabyin_admin_content_toggle",
        summary="فعال/غیرفعال کردن محتوا — ادمین",
        description=(
            "تغییر وضعیت نمایش یک محتوا در سایت عمومی.\n\n"
            "با این endpoint می‌توان محتوایی را از نمایش عمومی پنهان کرد "
            "بدون اینکه از دیتابیس حذف شود.\n\n"
            "پس از تغییر، cache عمومی به‌صورت خودکار invalidate می‌شود."
        ),
        tags=[TAG_TABYIN_ADMIN],
        request=AdminTabyinContentToggleSerializer,
        responses={
            200: build_success_response_serializer(
                name="AdminTabyinContentToggleResponse",
                data_serializer=AdminTabyinContentDetailSerializer,
            ),
            400: build_error_response_serializer(
                name="AdminTabyinContentToggleBadRequestResponse",
            ),
            403: build_error_response_serializer(
                name="AdminTabyinContentToggleForbiddenResponse",
            ),
            404: build_error_response_serializer(
                name="AdminTabyinContentToggleNotFoundResponse",
            ),
        },
    )
)
class AdminTabyinContentToggleView(APIView):
    """فعال/غیرفعال کردن محتوا — ادمین."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    def patch(
        self,
        request: Request,
        external_id: str,
    ) -> SuccessResponse | ErrorResponse:
        content = selectors.get_admin_content_by_external_id(external_id)
        if content is None:
            return ErrorResponse(
                message="محتوا یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = AdminTabyinContentToggleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        old_is_active = content.is_active
        new_is_active = serializer.validated_data["is_active"]

        content = services.toggle_content_visibility(
            content=content,
            is_active=new_is_active,
        )

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.TABYIN_CONTENT_TOGGLED,
            resource_type="tabyin_content",
            resource_id=external_id,
            changes={
                "is_active": {"before": old_is_active, "after": new_is_active},
            },
            **metadata,
        )

        detail_serializer = AdminTabyinContentDetailSerializer(content)
        return SuccessResponse(
            data=detail_serializer.data,
            message="وضعیت محتوا با موفقیت تغییر کرد.",
        )


# ============================================================
# Admin Views — User submission review
# ============================================================


class AdminTabyinSubmissionQueueView(APIView):
    """Admin review queue for user-submitted Tabyin content."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(
        operation_id="tabyin_admin_submissions_queue",
        summary="صف بررسی محتواهای ارسالی کاربران",
        tags=[TAG_TABYIN_ADMIN],
        responses={
            200: build_paginated_success_response_serializer(
                name="AdminTabyinSubmissionQueueResponse",
                item_serializer=AdminTabyinSubmissionQueueSerializer,
            ),
        },
    )
    def get(self, request: Request) -> SuccessResponse:
        queryset = selectors.get_admin_user_submissions_queue()
        status_filter = request.query_params.get("submission_status")
        if status_filter:
            queryset = queryset.filter(submission_status=status_filter)

        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = AdminTabyinSubmissionQueueSerializer(page, many=True)
        return paginator.get_paginated_response(
            serializer.data,
            message="صف بررسی محتواهای ارسالی با موفقیت دریافت شد.",
        )


class AdminTabyinSubmissionDetailView(APIView):
    """Admin detail view for one user-submitted content item."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(
        operation_id="tabyin_admin_submission_retrieve",
        summary="جزئیات محتوای ارسالی کاربر",
        tags=[TAG_TABYIN_ADMIN],
        responses={
            200: build_success_response_serializer(
                name="AdminTabyinSubmissionDetailResponse",
                data_serializer=AdminTabyinSubmissionQueueSerializer,
            ),
            404: build_error_response_serializer(name="AdminTabyinSubmissionNotFound"),
        },
    )
    def get(self, request: Request, content_id: int) -> SuccessResponse | ErrorResponse:
        content = selectors.get_admin_user_submission_by_id(content_id)
        if content is None:
            return ErrorResponse(
                message="محتوای ارسالی یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return SuccessResponse(data=AdminTabyinSubmissionQueueSerializer(content).data)


class AdminTabyinSubmissionApproveView(APIView):
    """Approve a pending user-submitted Tabyin content item."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(
        operation_id="tabyin_admin_submission_approve",
        summary="تأیید محتوای ارسالی کاربر",
        tags=[TAG_TABYIN_ADMIN],
        request=AdminTabyinSubmissionReviewSerializer,
        responses={
            200: build_success_response_serializer(
                name="AdminTabyinSubmissionApproveResponse",
                data_serializer=AdminTabyinSubmissionQueueSerializer,
            ),
            400: build_error_response_serializer(name="AdminTabyinSubmissionReviewBadRequest"),
            404: build_error_response_serializer(name="AdminTabyinSubmissionReviewNotFound"),
        },
    )
    def post(self, request: Request, content_id: int) -> SuccessResponse | ErrorResponse:
        content = selectors.get_admin_user_submission_by_id(content_id)
        if content is None:
            return ErrorResponse(message="محتوای ارسالی یافت نشد.", status_code=404)
        serializer = AdminTabyinSubmissionReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            content = services.approve_user_submission(
                content=content,
                admin=request.user,
                admin_note=serializer.validated_data.get("admin_note", ""),
            )
        except services.SubmissionNotReviewable as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.TABYIN_USER_SUBMISSION_APPROVED,
            resource_type="tabyin_content",
            resource_id=str(content.pk),
            **metadata,
        )
        return SuccessResponse(
            data=AdminTabyinSubmissionQueueSerializer(content).data,
            message="محتوای ارسالی با موفقیت تأیید شد.",
        )


class AdminTabyinSubmissionRejectView(APIView):
    """Reject a pending user-submitted Tabyin content item."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(
        operation_id="tabyin_admin_submission_reject",
        summary="رد محتوای ارسالی کاربر",
        tags=[TAG_TABYIN_ADMIN],
        request=AdminTabyinSubmissionReviewSerializer,
        responses={
            200: build_success_response_serializer(
                name="AdminTabyinSubmissionRejectResponse",
                data_serializer=AdminTabyinSubmissionQueueSerializer,
            ),
            400: build_error_response_serializer(name="AdminTabyinSubmissionRejectBadRequest"),
            404: build_error_response_serializer(name="AdminTabyinSubmissionRejectNotFound"),
        },
    )
    def post(self, request: Request, content_id: int) -> SuccessResponse | ErrorResponse:
        content = selectors.get_admin_user_submission_by_id(content_id)
        if content is None:
            return ErrorResponse(message="محتوای ارسالی یافت نشد.", status_code=404)
        serializer = AdminTabyinSubmissionReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            content = services.reject_user_submission(
                content=content,
                admin=request.user,
                admin_note=serializer.validated_data.get("admin_note", ""),
            )
        except services.SubmissionNotReviewable as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.TABYIN_USER_SUBMISSION_REJECTED,
            resource_type="tabyin_content",
            resource_id=str(content.pk),
            **metadata,
        )
        return SuccessResponse(
            data=AdminTabyinSubmissionQueueSerializer(content).data,
            message="محتوای ارسالی رد شد.",
        )


# ============================================================
# Admin Views — Async Sync
# ============================================================


@extend_schema_view(
    post=extend_schema(
        operation_id="tabyin_admin_sync_dispatch",
        summary="اجرای دستی همگام‌سازی (غیرهمزمان) — ادمین",
        description=(
            "اجرای همگام‌سازی محتوا از سایت محتوانگار به‌صورت **غیرهمزمان**.\n\n"
            "این endpoint task مربوط به sync را در صف Celery قرار می‌دهد و "
            "بلافاصله پاسخ می‌دهد. خود اجرای sync در پس‌زمینه انجام می‌شود.\n\n"
            "**حالت‌های موجود:**\n"
            "- `full`: همه صفحات پیمایش می‌شوند (سنگین‌تر)\n"
            "- `incremental`: فقط تغییرات اخیر (سریع‌تر)\n\n"
            "برای پیگیری وضعیت اجرا از endpoint وضعیت task استفاده کنید.\n\n"
            "پس از sync (در صورت وجود تغییر)، cache عمومی به‌صورت خودکار "
            "invalidate می‌شود.\n\n"
            "**Throttle:** حداکثر ۵ بار در ساعت."
        ),
        tags=[TAG_TABYIN_ADMIN],
        request=AdminSyncTriggerSerializer,
        responses={
            202: build_success_response_serializer(
                name="AdminSyncDispatchResponse",
                data_serializer=AdminSyncTaskDispatchedSerializer,
            ),
            400: build_error_response_serializer(
                name="AdminSyncDispatchBadRequestResponse",
            ),
            403: build_error_response_serializer(
                name="AdminSyncDispatchForbiddenResponse",
            ),
            429: build_error_response_serializer(
                name="AdminSyncDispatchThrottledResponse",
            ),
        },
    )
)
class AdminSyncTriggerView(APIView):
    """اجرای دستی sync به‌صورت async از طریق Celery — ادمین."""

    permission_classes = [IsAuthenticated, IsAdminUser]
    throttle_classes = [TabyinSyncThrottle]

    def post(self, request: Request) -> SuccessResponse:
        serializer = AdminSyncTriggerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        mode = serializer.validated_data.get("mode", "incremental")

        logger.info(
            "Async sync dispatch requested by user_id=%s mode=%s",
            request.user.pk,
            mode,
        )

        metadata = extract_audit_metadata(request)

        task_id = services.dispatch_sync_task(
            mode=mode,
            triggered_by_user_id=request.user.pk,
            request_id=metadata["request_id"],
            dispatch_ip=metadata["ip_address"],
        )

        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.TABYIN_SYNC_DISPATCHED,
            resource_type="tabyin_sync",
            resource_id=task_id,
            extra_data={"mode": mode},
            **metadata,
        )

        status_url = reverse(
            "tabyin:admin-sync-status",
            kwargs={"task_id": task_id},
            request=request,
        )

        payload_serializer = AdminSyncTaskDispatchedSerializer(
            data={
                "task_id": task_id,
                "mode": mode,
                "status_url": status_url,
            }
        )
        payload_serializer.is_valid(raise_exception=True)

        return SuccessResponse(
            data=payload_serializer.data,
            status_code=status.HTTP_202_ACCEPTED,
            message="درخواست همگام‌سازی در صف اجرا قرار گرفت.",
        )


@extend_schema_view(
    get=extend_schema(
        operation_id="tabyin_admin_sync_status",
        summary="پیگیری وضعیت task همگام‌سازی — ادمین",
        description=(
            "نمایش وضعیت لحظه‌ای یک task پس‌زمینه‌ی sync.\n\n"
            "**مقادیر ممکن `state`:**\n"
            "- `PENDING`: هنوز اجرا نشده یا task_id نامعتبر است.\n"
            "- `STARTED`: در حال اجراست.\n"
            "- `RETRY`: درحال تلاش مجدد پس از خطا.\n"
            "- `SUCCESS`: با موفقیت تمام شده — `result` شامل آمار sync است.\n"
            "- `FAILURE`: شکست خورده — `error` شامل پیام خطاست.\n"
            "- `REVOKED`: لغو شده.\n\n"
            "برای taskهای ناتمام، فیلدهای `result` و `error` خالی هستند."
        ),
        tags=[TAG_TABYIN_ADMIN],
        responses={
            200: build_success_response_serializer(
                name="AdminSyncStatusResponse",
                data_serializer=AdminSyncTaskStatusSerializer,
            ),
            403: build_error_response_serializer(
                name="AdminSyncStatusForbiddenResponse",
            ),
        },
    )
)
class AdminSyncTaskStatusView(APIView):
    """پیگیری وضعیت یک task sync — ادمین."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request: Request, task_id: str) -> SuccessResponse:
        status_payload = services.get_sync_task_status(task_id=task_id)

        serializer = AdminSyncTaskStatusSerializer(data=status_payload)
        serializer.is_valid(raise_exception=True)

        return SuccessResponse(data=serializer.data)
