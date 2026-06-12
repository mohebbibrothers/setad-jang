"""API views for user activity timeline."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.activity import selectors
from apps.activity.filters import UserActivityFilter
from apps.activity.permissions import IsActivityAdminUser
from apps.activity.serializers import UserActivitySerializer
from apps.core.pagination import StandardPagination


class UserActivityTimelineView(APIView):
    """Current user's activity timeline."""

    permission_classes = [IsAuthenticated]
    serializer_class = UserActivitySerializer

    def get(self, request) -> Response:
        """Return paginated current-user activity events."""
        queryset = selectors.get_user_activities(user_id=request.user.pk)
        filterset = UserActivityFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(UserActivitySerializer(page, many=True).data)


class AdminActivityTimelineView(APIView):
    """Admin all-users activity timeline."""

    permission_classes = [IsActivityAdminUser]
    serializer_class = UserActivitySerializer

    def get(self, request) -> Response:
        """Return paginated admin activity timeline."""
        queryset = selectors.get_admin_activities()
        filterset = UserActivityFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(UserActivitySerializer(page, many=True).data)
