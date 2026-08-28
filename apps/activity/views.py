"""API views for user activity timeline."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.activity import selectors
from apps.activity.filters import UserActivityFilter
from apps.activity.permissions import IsActivityAdminUser
from apps.activity.serializers import UserActivitySerializer
from apps.core.pagination import StandardPagination
from apps.core.views import paginated_list_response


class UserActivityTimelineView(APIView):
    """Current user's activity timeline."""

    permission_classes = [IsAuthenticated]
    serializer_class = UserActivitySerializer

    def get(self, request) -> Response:
        """Return paginated current-user activity events."""
        return paginated_list_response(
            request=request,
            view=self,
            queryset=selectors.get_user_activities(user_id=request.user.pk),
            serializer_class=UserActivitySerializer,
            pagination_class=StandardPagination,
            filterset_class=UserActivityFilter,
        )


class AdminActivityTimelineView(APIView):
    """Admin all-users activity timeline."""

    permission_classes = [IsActivityAdminUser]
    serializer_class = UserActivitySerializer

    def get(self, request) -> Response:
        """Return paginated admin activity timeline."""
        return paginated_list_response(
            request=request,
            view=self,
            queryset=selectors.get_admin_activities(),
            serializer_class=UserActivitySerializer,
            pagination_class=StandardPagination,
            filterset_class=UserActivityFilter,
        )
