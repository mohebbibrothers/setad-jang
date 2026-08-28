"""API views for notification inbox and admin inspection."""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import StandardPagination
from apps.core.responses import CreatedResponse, ErrorResponse, SuccessResponse
from apps.core.views import paginated_list_response
from apps.notifications import selectors, services
from apps.notifications.permissions import IsNotificationAdminUser
from apps.notifications.serializers import (
    NotificationDeliverySerializer,
    NotificationEventSerializer,
    NotificationPreferenceInputSerializer,
    NotificationPreferenceSerializer,
    NotificationTemplateSerializer,
)


class NotificationInboxView(APIView):
    """Current user's notification inbox."""

    permission_classes = [IsAuthenticated]
    serializer_class = NotificationDeliverySerializer

    def get(self, request) -> Response:
        """Return paginated notifications."""
        return paginated_list_response(
            request=request,
            view=self,
            queryset=selectors.get_user_deliveries(user_id=request.user.pk),
            serializer_class=NotificationDeliverySerializer,
            pagination_class=StandardPagination,
        )


class NotificationMarkReadView(APIView):
    """Mark one notification as read."""

    permission_classes = [IsAuthenticated]
    serializer_class = NotificationDeliverySerializer

    def post(self, request, delivery_id: int) -> SuccessResponse | ErrorResponse:
        """Mark a user-owned delivery as read."""
        delivery = selectors.get_user_delivery_by_id(
            user_id=request.user.pk, delivery_id=delivery_id
        )
        if delivery is None:
            return ErrorResponse(message="اعلان یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        delivery = services.mark_delivery_read(delivery=delivery, user=request.user)
        return SuccessResponse(
            data=NotificationDeliverySerializer(delivery).data, message="اعلان خوانده شد."
        )


class NotificationMarkAllReadView(APIView):
    """Mark all current user's notifications as read."""

    permission_classes = [IsAuthenticated]
    serializer_class = NotificationDeliverySerializer

    def post(self, request) -> SuccessResponse:
        """Mark all deliveries as read."""
        updated = services.mark_all_read(user=request.user)
        return SuccessResponse(data={"updated": updated}, message="همه اعلان‌ها خوانده شد.")


class NotificationPreferenceListSetView(APIView):
    """Current user's notification preferences."""

    permission_classes = [IsAuthenticated]
    serializer_class = NotificationPreferenceSerializer

    def get(self, request) -> SuccessResponse:
        """Return preferences."""
        return SuccessResponse(
            data=NotificationPreferenceSerializer(
                selectors.get_user_preferences(user_id=request.user.pk), many=True
            ).data
        )

    def post(self, request) -> CreatedResponse:
        """Create/update one preference."""
        serializer = NotificationPreferenceInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        preference = services.set_preference(user=request.user, **serializer.validated_data)
        return CreatedResponse(
            data=NotificationPreferenceSerializer(preference).data, message="تنظیم اعلان ذخیره شد."
        )


class NotificationAdminEventListView(APIView):
    """Admin event inspection."""

    permission_classes = [IsNotificationAdminUser]
    serializer_class = NotificationEventSerializer

    def get(self, request) -> Response:
        """Return notification events."""
        paginator = StandardPagination()
        page = paginator.paginate_queryset(selectors.get_admin_events(), request, view=self)
        return paginator.get_paginated_response(NotificationEventSerializer(page, many=True).data)


class NotificationAdminDeliveryListView(APIView):
    """Admin delivery inspection."""

    permission_classes = [IsNotificationAdminUser]
    serializer_class = NotificationDeliverySerializer

    def get(self, request) -> Response:
        """Return notification deliveries."""
        paginator = StandardPagination()
        page = paginator.paginate_queryset(selectors.get_admin_deliveries(), request, view=self)
        return paginator.get_paginated_response(
            NotificationDeliverySerializer(page, many=True).data
        )


class NotificationAdminTemplateListView(APIView):
    """Admin template inspection."""

    permission_classes = [IsNotificationAdminUser]
    serializer_class = NotificationTemplateSerializer

    def get(self, request) -> SuccessResponse:
        """Return templates."""
        return SuccessResponse(
            data=NotificationTemplateSerializer(selectors.get_admin_templates(), many=True).data
        )
