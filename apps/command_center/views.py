"""API views for unified admin command center."""

from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from apps.command_center.permissions import IsCommandCenterAdminUser
from apps.command_center.selectors import get_command_center_summary
from apps.command_center.serializers import CommandCenterSummarySerializer
from apps.core.responses import SuccessResponse
from apps.core.schemas import build_success_response_serializer

TAG_COMMAND_CENTER = "مرکز فرماندهی مدیریت"
COMMAND_CENTER_RESPONSE = build_success_response_serializer(
    name="CommandCenterSummaryResponse", data_serializer=CommandCenterSummarySerializer
)


class CommandCenterSummaryView(APIView):
    """Unified cross-app admin command center endpoint."""

    permission_classes = [IsCommandCenterAdminUser]
    serializer_class = CommandCenterSummarySerializer

    @extend_schema(
        operation_id="admin_command_center_summary",
        tags=[TAG_COMMAND_CENTER],
        responses={200: COMMAND_CENTER_RESPONSE},
    )
    def get(self, request) -> SuccessResponse:
        """Return cross-app operational summary."""
        return SuccessResponse(
            data=get_command_center_summary(), message="خلاصه مرکز فرماندهی دریافت شد."
        )
