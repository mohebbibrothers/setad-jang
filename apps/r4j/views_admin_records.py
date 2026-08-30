"""گروه دامنه‌ای `views_admin_records` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import (
    extend_schema,
)
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.core.responses import (
    CreatedResponse,
    DeletedResponse,
    ErrorResponse,
    SuccessResponse,
)

from . import selectors, services
from .permissions import IsR4JAdminUser
from .serializers import (
    R4JAdminAttachmentSerializer,
    R4JAdminFieldVisibilitySerializer,
    R4JAdminPhoneSerializer,
    R4JAdminPhotoSerializer,
    R4JAdminSocialSerializer,
    R4JAliasCreateSerializer,
    R4JAliasSerializer,
    R4JAttachmentCreateSerializer,
    R4JFieldVisibilityUpsertSerializer,
    R4JPhoneCreateSerializer,
    R4JPhoneUpdateSerializer,
    R4JPhotoCreateSerializer,
    R4JSocialCreateSerializer,
    R4JSocialUpdateSerializer,
)
from .services import (
    R4JServiceError,
)
from .views_common import (  # noqa: F401 — re-exportِ رایگان برای بدنه‌های منتقل‌شده
    ADMIN_ALIAS_LIST_RESPONSE,
    ADMIN_ALIAS_RESPONSE,
    ADMIN_ATTACHMENT_LIST_RESPONSE,
    ADMIN_ATTACHMENT_RESPONSE,
    ADMIN_BOUNTY_DETAIL_RESPONSE,
    ADMIN_BOUNTY_FILTER_PARAMS,
    ADMIN_BOUNTY_LIST_RESPONSE,
    ADMIN_CUSTODY_EVENT_LIST_RESPONSE,
    ADMIN_CUSTODY_EVENT_RESPONSE,
    ADMIN_DETAIL_RESPONSE,
    ADMIN_LIST_FILTER_PARAMS,
    ADMIN_LIST_RESPONSE,
    ADMIN_PHONE_LIST_RESPONSE,
    ADMIN_PHONE_RESPONSE,
    ADMIN_PHOTO_LIST_RESPONSE,
    ADMIN_PHOTO_RESPONSE,
    ADMIN_REPORT_DETAIL_RESPONSE,
    ADMIN_REPORT_FILTER_PARAMS,
    ADMIN_REPORT_LIST_RESPONSE,
    ADMIN_SOCIAL_LIST_RESPONSE,
    ADMIN_SOCIAL_RESPONSE,
    ADMIN_VISIBILITY_LIST_RESPONSE,
    ADMIN_VISIBILITY_RESPONSE,
    EMPTY_SUCCESS_RESPONSE,
    GENERIC_ERROR_RESPONSE,
    LIST_PAGINATION_PARAMS,
    PUBLIC_DETAIL_RESPONSE,
    PUBLIC_LIST_FILTER_PARAMS,
    PUBLIC_LIST_RESPONSE,
    TAG_R4J_ADMIN,
    TAG_R4J_BOUNTY,
    TAG_R4J_PUBLIC,
    TAG_R4J_USER,
    USER_BOUNTY_DETAIL_RESPONSE,
    USER_BOUNTY_FILTER_PARAMS,
    USER_BOUNTY_LIST_RESPONSE,
    USER_REPORT_DETAIL_RESPONSE,
    USER_REPORT_FILTER_PARAMS,
    USER_REPORT_LIST_RESPONSE,
    _build_filters_signature,
)

# ============================================================
# Admin — Nested: Aliases
# ============================================================


class R4JAdminAliasListCreateView(APIView):
    """list + create aliases — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_aliases_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست اسامی مستعار",
        responses={200: ADMIN_ALIAS_LIST_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        aliases = selectors.get_admin_aliases(criminal_id=criminal_id)
        return SuccessResponse(
            data=R4JAliasSerializer(aliases, many=True).data,
            message="لیست اسامی مستعار با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="r4j_admin_aliases_create",
        tags=[TAG_R4J_ADMIN],
        summary="افزودن نام مستعار",
        request=R4JAliasCreateSerializer,
        responses={
            201: ADMIN_ALIAS_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JAliasCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alias = services.add_alias(
            criminal=criminal,
            alias=serializer.validated_data["alias"],
        )
        return CreatedResponse(
            data=R4JAliasSerializer(alias).data,
            message="نام مستعار با موفقیت اضافه شد.",
        )


class R4JAdminAliasDeleteView(APIView):
    """delete one alias — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_aliases_delete",
        tags=[TAG_R4J_ADMIN],
        summary="حذف نام مستعار",
        responses={200: EMPTY_SUCCESS_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def delete(self, request: Request, criminal_id: int, alias_id: int) -> Response:
        alias_obj = selectors.get_admin_alias_by_id(
            criminal_id=criminal_id,
            alias_id=alias_id,
        )
        if alias_obj is None:
            return ErrorResponse(
                message="نام مستعاری با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        services.remove_alias(alias_obj=alias_obj)
        return DeletedResponse(message="نام مستعار با موفقیت حذف شد.")


# ============================================================
# Admin — Nested: Phones
# ============================================================


class R4JAdminPhoneListCreateView(APIView):
    """list + create phones — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_phones_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست شماره‌های تماس",
        responses={200: ADMIN_PHONE_LIST_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        phones = selectors.get_admin_phones(criminal_id=criminal_id)
        return SuccessResponse(
            data=R4JAdminPhoneSerializer(phones, many=True).data,
            message="لیست شماره‌ها با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="r4j_admin_phones_create",
        tags=[TAG_R4J_ADMIN],
        summary="افزودن شماره تماس",
        request=R4JPhoneCreateSerializer,
        responses={
            201: ADMIN_PHONE_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JPhoneCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = services.add_phone(criminal=criminal, **serializer.validated_data)

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_PHONE_ADDED,
            resource_type="r4j_criminal_phone",
            resource_id=str(phone.pk),
            extra_data={"criminal_id": criminal_id},
            **metadata,
        )

        return CreatedResponse(
            data=R4JAdminPhoneSerializer(phone).data,
            message="شماره تماس با موفقیت اضافه شد.",
        )


class R4JAdminPhoneDetailView(APIView):
    """update + delete phone — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_phones_update",
        tags=[TAG_R4J_ADMIN],
        summary="ویرایش شماره تماس",
        request=R4JPhoneUpdateSerializer,
        responses={
            200: ADMIN_PHONE_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def patch(self, request: Request, criminal_id: int, phone_id: int) -> Response:
        phone = selectors.get_admin_phone_by_id(
            criminal_id=criminal_id,
            phone_id=phone_id,
        )
        if phone is None:
            return ErrorResponse(
                message="شماره‌ای با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JPhoneUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        phone = services.update_phone(phone=phone, **serializer.validated_data)
        return SuccessResponse(
            data=R4JAdminPhoneSerializer(phone).data,
            message="شماره تماس با موفقیت بروزرسانی شد.",
        )

    @extend_schema(
        operation_id="r4j_admin_phones_delete",
        tags=[TAG_R4J_ADMIN],
        summary="حذف شماره تماس",
        responses={200: EMPTY_SUCCESS_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def delete(self, request: Request, criminal_id: int, phone_id: int) -> Response:
        phone = selectors.get_admin_phone_by_id(
            criminal_id=criminal_id,
            phone_id=phone_id,
        )
        if phone is None:
            return ErrorResponse(
                message="شماره‌ای با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        services.remove_phone(phone=phone)

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_PHONE_REMOVED,
            resource_type="r4j_criminal_phone",
            resource_id=str(phone_id),
            extra_data={"criminal_id": criminal_id},
            **metadata,
        )
        return DeletedResponse(message="شماره با موفقیت حذف شد.")


# ============================================================
# Admin — Nested: Socials
# ============================================================


class R4JAdminSocialListCreateView(APIView):
    """list + create socials — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_socials_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست شبکه‌های اجتماعی",
        responses={200: ADMIN_SOCIAL_LIST_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        socials = selectors.get_admin_socials(criminal_id=criminal_id)
        return SuccessResponse(
            data=R4JAdminSocialSerializer(socials, many=True).data,
            message="لیست شبکه‌ها با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="r4j_admin_socials_create",
        tags=[TAG_R4J_ADMIN],
        summary="افزودن شبکه اجتماعی",
        request=R4JSocialCreateSerializer,
        responses={
            201: ADMIN_SOCIAL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JSocialCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            social = services.add_social(criminal=criminal, **serializer.validated_data)
        except R4JServiceError as exc:
            return ErrorResponse(message=str(exc))

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_SOCIAL_ADDED,
            resource_type="r4j_criminal_social",
            resource_id=str(social.pk),
            extra_data={"criminal_id": criminal_id, "platform": social.platform},
            **metadata,
        )

        return CreatedResponse(
            data=R4JAdminSocialSerializer(social).data,
            message="شبکه اجتماعی با موفقیت اضافه شد.",
        )


class R4JAdminSocialDetailView(APIView):
    """update + delete social — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_socials_update",
        tags=[TAG_R4J_ADMIN],
        summary="ویرایش شبکه اجتماعی",
        request=R4JSocialUpdateSerializer,
        responses={
            200: ADMIN_SOCIAL_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def patch(self, request: Request, criminal_id: int, social_id: int) -> Response:
        social = selectors.get_admin_social_by_id(
            criminal_id=criminal_id,
            social_id=social_id,
        )
        if social is None:
            return ErrorResponse(
                message="شبکه‌ای با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JSocialUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        social = services.update_social(social=social, **serializer.validated_data)
        return SuccessResponse(
            data=R4JAdminSocialSerializer(social).data,
            message="شبکه اجتماعی با موفقیت بروزرسانی شد.",
        )

    @extend_schema(
        operation_id="r4j_admin_socials_delete",
        tags=[TAG_R4J_ADMIN],
        summary="حذف شبکه اجتماعی",
        responses={200: EMPTY_SUCCESS_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def delete(self, request: Request, criminal_id: int, social_id: int) -> Response:
        social = selectors.get_admin_social_by_id(
            criminal_id=criminal_id,
            social_id=social_id,
        )
        if social is None:
            return ErrorResponse(
                message="شبکه‌ای با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        services.remove_social(social=social)

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_SOCIAL_REMOVED,
            resource_type="r4j_criminal_social",
            resource_id=str(social_id),
            extra_data={"criminal_id": criminal_id},
            **metadata,
        )
        return DeletedResponse(message="شبکه اجتماعی با موفقیت حذف شد.")


# ============================================================
# Admin — Nested: Photos
# ============================================================


class R4JAdminPhotoListCreateView(APIView):
    """list + upload photo — admin."""

    permission_classes = [IsR4JAdminUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(
        operation_id="r4j_admin_photos_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست عکس‌ها",
        responses={200: ADMIN_PHOTO_LIST_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        photos = selectors.get_admin_photos(criminal_id=criminal_id)
        return SuccessResponse(
            data=R4JAdminPhotoSerializer(photos, many=True).data,
            message="لیست عکس‌ها با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="r4j_admin_photos_create",
        tags=[TAG_R4J_ADMIN],
        summary="آپلود عکس",
        request=R4JPhotoCreateSerializer,
        responses={
            201: ADMIN_PHOTO_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JPhotoCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        photo = services.add_photo(criminal=criminal, **serializer.validated_data)

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_PHOTO_ADDED,
            resource_type="r4j_criminal_photo",
            resource_id=str(photo.pk),
            extra_data={"criminal_id": criminal_id, "is_primary": photo.is_primary},
            **metadata,
        )

        return CreatedResponse(
            data=R4JAdminPhotoSerializer(photo).data,
            message="عکس با موفقیت اضافه شد.",
        )


class R4JAdminPhotoDetailView(APIView):
    """delete photo — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_photos_delete",
        tags=[TAG_R4J_ADMIN],
        summary="حذف عکس",
        responses={200: EMPTY_SUCCESS_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def delete(self, request: Request, criminal_id: int, photo_id: int) -> Response:
        photo = selectors.get_admin_photo_by_id(
            criminal_id=criminal_id,
            photo_id=photo_id,
        )
        if photo is None:
            return ErrorResponse(
                message="عکسی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        services.remove_photo(photo=photo)

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_PHOTO_REMOVED,
            resource_type="r4j_criminal_photo",
            resource_id=str(photo_id),
            extra_data={"criminal_id": criminal_id},
            **metadata,
        )
        return DeletedResponse(message="عکس با موفقیت حذف شد.")


class R4JAdminPhotoSetPrimaryView(APIView):
    """set a photo as primary — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_photos_set_primary",
        tags=[TAG_R4J_ADMIN],
        summary="تنظیم عکس به‌عنوان اصلی",
        request=None,
        responses={200: ADMIN_PHOTO_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def post(self, request: Request, criminal_id: int, photo_id: int) -> Response:
        photo = selectors.get_admin_photo_by_id(
            criminal_id=criminal_id,
            photo_id=photo_id,
        )
        if photo is None:
            return ErrorResponse(
                message="عکسی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        photo = services.set_primary_photo(photo=photo)
        return SuccessResponse(
            data=R4JAdminPhotoSerializer(photo).data,
            message="عکس به‌عنوان اصلی تنظیم شد.",
        )


# ============================================================
# Admin — Nested: Attachments
# ============================================================


class R4JAdminAttachmentListCreateView(APIView):
    """list + upload attachment — admin."""

    permission_classes = [IsR4JAdminUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(
        operation_id="r4j_admin_attachments_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست اسناد",
        responses={200: ADMIN_ATTACHMENT_LIST_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        attachments = selectors.get_admin_attachments(criminal_id=criminal_id)
        return SuccessResponse(
            data=R4JAdminAttachmentSerializer(attachments, many=True).data,
            message="لیست اسناد با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="r4j_admin_attachments_create",
        tags=[TAG_R4J_ADMIN],
        summary="آپلود سند",
        request=R4JAttachmentCreateSerializer,
        responses={
            201: ADMIN_ATTACHMENT_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JAttachmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attachment = services.add_attachment(
            criminal=criminal,
            uploaded_by=request.user,
            **serializer.validated_data,
        )
        return CreatedResponse(
            data=R4JAdminAttachmentSerializer(attachment).data,
            message="سند با موفقیت اضافه شد.",
        )


class R4JAdminAttachmentDetailView(APIView):
    """delete attachment — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_attachments_delete",
        tags=[TAG_R4J_ADMIN],
        summary="حذف سند",
        responses={200: EMPTY_SUCCESS_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def delete(
        self,
        request: Request,
        criminal_id: int,
        attachment_id: int,
    ) -> Response:
        attachment = selectors.get_admin_attachment_by_id(
            criminal_id=criminal_id,
            attachment_id=attachment_id,
        )
        if attachment is None:
            return ErrorResponse(
                message="سندی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        services.remove_attachment(attachment=attachment)
        return DeletedResponse(message="سند با موفقیت حذف شد.")


# ============================================================
# Admin — Field Visibility
# ============================================================


class R4JAdminFieldVisibilityListUpsertView(APIView):
    """list + upsert visibility — admin."""

    permission_classes = [IsR4JAdminUser]

    @extend_schema(
        operation_id="r4j_admin_visibility_list",
        tags=[TAG_R4J_ADMIN],
        summary="لیست تنظیمات نمایش فیلدها",
        responses={200: ADMIN_VISIBILITY_LIST_RESPONSE, 404: GENERIC_ERROR_RESPONSE},
    )
    def get(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        items = selectors.get_admin_field_visibility(criminal_id=criminal_id)
        return SuccessResponse(
            data=R4JAdminFieldVisibilitySerializer(items, many=True).data,
            message="لیست با موفقیت دریافت شد.",
        )

    @extend_schema(
        operation_id="r4j_admin_visibility_upsert",
        tags=[TAG_R4J_ADMIN],
        summary="تنظیم نمایش یک فیلد",
        request=R4JFieldVisibilityUpsertSerializer,
        responses={
            200: ADMIN_VISIBILITY_RESPONSE,
            400: GENERIC_ERROR_RESPONSE,
            404: GENERIC_ERROR_RESPONSE,
        },
    )
    def patch(self, request: Request, criminal_id: int) -> Response:
        criminal = selectors.get_admin_criminal_by_id(criminal_id)
        if criminal is None:
            return ErrorResponse(
                message="مجرمی با این شناسه یافت نشد.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = R4JFieldVisibilityUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        obj = services.upsert_field_visibility(
            criminal=criminal,
            field_name=serializer.validated_data["field_name"],
            is_public=serializer.validated_data["is_public"],
        )

        metadata = extract_audit_metadata(request)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_CRIMINAL_VISIBILITY_CHANGED,
            resource_type="r4j_criminal_field_visibility",
            resource_id=str(obj.pk),
            changes={
                "field_name": serializer.validated_data["field_name"],
                "is_public": serializer.validated_data["is_public"],
            },
            extra_data={"criminal_id": criminal_id},
            **metadata,
        )

        return SuccessResponse(
            data=R4JAdminFieldVisibilitySerializer(obj).data,
            message="تنظیم نمایش با موفقیت اعمال شد.",
        )
