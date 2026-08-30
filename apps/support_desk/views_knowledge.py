"""گروه دامنه‌ای `views_knowledge` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from django.db.models import Q
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
from apps.support_desk import selectors, services
from apps.support_desk.permissions import IsSupportAdminUser
from apps.support_desk.serializers import (
    SupportKnowledgeArticleInputSerializer,
    SupportKnowledgeArticleSerializer,
    SupportKnowledgeArticleUseInputSerializer,
    SupportKnowledgeArticleUseSerializer,
    SupportKnowledgeRecommendationSerializer,
)

from .views_common import (  # noqa: F401 — re-exportِ رایگان برای بدنه‌های منتقل‌شده
    ADMIN_ANALYTICS_RESPONSE,
    ADMIN_CANNED_RESPONSE,
    ADMIN_CATEGORY_RESPONSE,
    ADMIN_DEPARTMENT_RESPONSE,
    ADMIN_DUPLICATE_RESPONSE,
    ADMIN_SLA_RESPONSE,
    ADMIN_TICKET_DETAIL_RESPONSE,
    ADMIN_TICKET_LIST_RESPONSE,
    ADMIN_TICKET_TYPE_RESPONSE,
    ASSIGNMENT_RECOMMENDATION_RESPONSE,
    ATTACHMENT_RESPONSE,
    CATEGORY_LIST_RESPONSE,
    DEPARTMENT_LIST_RESPONSE,
    KNOWLEDGE_ARTICLE_DETAIL_RESPONSE,
    KNOWLEDGE_ARTICLE_LIST_RESPONSE,
    KNOWLEDGE_ARTICLE_USE_RESPONSE,
    MESSAGE_LIST_RESPONSE,
    SMART_REPLY_BUNDLE_RESPONSE,
    SUPPORT_ERROR_RESPONSE,
    TAG_SUPPORT_TAXONOMY,
    TAG_SUPPORT_USER,
    TICKET_DETAIL_RESPONSE,
    TICKET_LIST_RESPONSE,
    TICKET_TYPE_LIST_RESPONSE,
    TRIAGE_RESPONSE,
    _get_user_ticket_or_error,
    _serialize_assignment_recommendation,
    _serialize_smart_reply_bundle,
    _service_error_response,
)


class SupportKnowledgeArticleListView(APIView):
    """Public/help-center knowledge article list endpoint."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="support_knowledge_articles_list",
        tags=[TAG_SUPPORT_USER],
        responses={200: KNOWLEDGE_ARTICLE_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """Return published knowledge articles with simple search/taxonomy filters."""
        queryset = selectors.get_published_knowledge_articles()
        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(summary__icontains=search)
                | Q(body__icontains=search)
            )
        department = request.query_params.get("department")
        if department:
            queryset = queryset.filter(department_id=department)
        category = request.query_params.get("category")
        if category:
            queryset = queryset.filter(category_id=category)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is not None:
            serializer = SupportKnowledgeArticleSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data, message="لیست مقالات پایگاه دانش دریافت شد."
            )
        return SuccessResponse(
            data=SupportKnowledgeArticleSerializer(queryset, many=True).data,
            message="لیست مقالات پایگاه دانش دریافت شد.",
        )


class SupportKnowledgeArticleDetailView(APIView):
    """Public/help-center knowledge article detail endpoint."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="support_knowledge_article_retrieve",
        tags=[TAG_SUPPORT_USER],
        responses={200: KNOWLEDGE_ARTICLE_DETAIL_RESPONSE, 404: SUPPORT_ERROR_RESPONSE},
    )
    def get(self, request: Request, slug: str) -> SuccessResponse | ErrorResponse:
        """Return one published knowledge article by slug."""
        article = selectors.get_public_knowledge_article_by_slug(slug=slug)
        if article is None:
            return ErrorResponse(
                message="مقاله‌ای با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        return SuccessResponse(
            data=SupportKnowledgeArticleSerializer(article).data,
            message="مقاله پایگاه دانش دریافت شد.",
        )


class SupportKnowledgeRecommendView(APIView):
    """Recommend knowledge articles for a draft/new support request."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="support_knowledge_articles_recommend",
        tags=[TAG_SUPPORT_USER],
        request=SupportKnowledgeRecommendationSerializer,
        responses={200: KNOWLEDGE_ARTICLE_LIST_RESPONSE},
    )
    def post(self, request: Request) -> SuccessResponse:
        """Recommend published articles from subject/description/taxonomy context."""
        serializer = SupportKnowledgeRecommendationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        articles = services.recommend_knowledge_articles(
            text=f"{serializer.validated_data['subject']} {serializer.validated_data['description']}",
            department=serializer.validated_data.get("department"),
            category=serializer.validated_data.get("category"),
            ticket_type=serializer.validated_data.get("ticket_type"),
        )
        return SuccessResponse(
            data=SupportKnowledgeArticleSerializer(articles, many=True).data,
            message="مقالات پیشنهادی پایگاه دانش دریافت شد.",
        )


class SupportAdminKnowledgeArticleListCreateView(APIView):
    """Admin knowledge article list/create endpoint."""

    permission_classes = [IsSupportAdminUser]

    @extend_schema(
        operation_id="support_admin_knowledge_articles_list",
        tags=[TAG_SUPPORT_TAXONOMY],
        responses={200: KNOWLEDGE_ARTICLE_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """Return all knowledge articles for admin management."""
        queryset = selectors.get_admin_knowledge_articles()
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is not None:
            serializer = SupportKnowledgeArticleSerializer(page, many=True)
            return paginator.get_paginated_response(
                serializer.data, message="لیست مقالات پایگاه دانش دریافت شد."
            )
        return SuccessResponse(
            data=SupportKnowledgeArticleSerializer(queryset, many=True).data,
            message="لیست مقالات پایگاه دانش دریافت شد.",
        )

    @extend_schema(
        operation_id="support_admin_knowledge_articles_create",
        tags=[TAG_SUPPORT_TAXONOMY],
        request=SupportKnowledgeArticleInputSerializer,
        responses={201: KNOWLEDGE_ARTICLE_DETAIL_RESPONSE, 400: SUPPORT_ERROR_RESPONSE},
    )
    def post(self, request: Request) -> CreatedResponse | ErrorResponse:
        """Create a knowledge base article."""
        serializer = SupportKnowledgeArticleInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            article = services.create_knowledge_article(**serializer.validated_data)
        except services.SupportDeskServiceError as exc:
            return _service_error_response(exc)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_KB_ARTICLE_CREATED,
            resource_type="support_knowledge_article",
            resource_id=str(article.pk),
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=SupportKnowledgeArticleSerializer(article).data,
            message="مقاله پایگاه دانش ایجاد شد.",
        )


class SupportAdminKnowledgeArticleDetailView(APIView):
    """Admin knowledge article retrieve/update endpoint."""

    permission_classes = [IsSupportAdminUser]

    @extend_schema(
        operation_id="support_admin_knowledge_article_retrieve",
        tags=[TAG_SUPPORT_TAXONOMY],
        responses={200: KNOWLEDGE_ARTICLE_DETAIL_RESPONSE, 404: SUPPORT_ERROR_RESPONSE},
    )
    def get(self, request: Request, article_id: int) -> SuccessResponse | ErrorResponse:
        """Return article detail for admin."""
        article = selectors.get_admin_knowledge_article_by_id(article_id=article_id)
        if article is None:
            return ErrorResponse(message="مقاله یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return SuccessResponse(data=SupportKnowledgeArticleSerializer(article).data)

    @extend_schema(
        operation_id="support_admin_knowledge_article_update",
        tags=[TAG_SUPPORT_TAXONOMY],
        request=SupportKnowledgeArticleInputSerializer,
        responses={
            200: KNOWLEDGE_ARTICLE_DETAIL_RESPONSE,
            400: SUPPORT_ERROR_RESPONSE,
            404: SUPPORT_ERROR_RESPONSE,
        },
    )
    def patch(self, request: Request, article_id: int) -> SuccessResponse | ErrorResponse:
        """Update article content/metadata."""
        article = selectors.get_admin_knowledge_article_by_id(article_id=article_id)
        if article is None:
            return ErrorResponse(message="مقاله یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportKnowledgeArticleInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            article = services.update_knowledge_article(
                article=article, **serializer.validated_data
            )
        except services.SupportDeskServiceError as exc:
            return _service_error_response(exc)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_KB_ARTICLE_UPDATED,
            resource_type="support_knowledge_article",
            resource_id=str(article.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportKnowledgeArticleSerializer(article).data,
            message="مقاله پایگاه دانش به‌روزرسانی شد.",
        )


class SupportAdminKnowledgeArticlePublishView(APIView):
    """Admin publish action for knowledge article."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportKnowledgeArticleSerializer

    @extend_schema(
        operation_id="support_admin_knowledge_article_publish",
        tags=[TAG_SUPPORT_TAXONOMY],
        request=None,
        responses={200: KNOWLEDGE_ARTICLE_DETAIL_RESPONSE, 404: SUPPORT_ERROR_RESPONSE},
    )
    def post(self, request: Request, article_id: int) -> SuccessResponse | ErrorResponse:
        """Publish one knowledge article."""
        article = selectors.get_admin_knowledge_article_by_id(article_id=article_id)
        if article is None:
            return ErrorResponse(message="مقاله یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        article = services.publish_knowledge_article(article=article)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_KB_ARTICLE_PUBLISHED,
            resource_type="support_knowledge_article",
            resource_id=str(article.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportKnowledgeArticleSerializer(article).data, message="مقاله منتشر شد."
        )


class SupportAdminKnowledgeArticleArchiveView(APIView):
    """Admin archive action for knowledge article."""

    permission_classes = [IsSupportAdminUser]
    serializer_class = SupportKnowledgeArticleSerializer

    @extend_schema(
        operation_id="support_admin_knowledge_article_archive",
        tags=[TAG_SUPPORT_TAXONOMY],
        request=None,
        responses={200: KNOWLEDGE_ARTICLE_DETAIL_RESPONSE, 404: SUPPORT_ERROR_RESPONSE},
    )
    def post(self, request: Request, article_id: int) -> SuccessResponse | ErrorResponse:
        """Archive one knowledge article."""
        article = selectors.get_admin_knowledge_article_by_id(article_id=article_id)
        if article is None:
            return ErrorResponse(message="مقاله یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        article = services.archive_knowledge_article(article=article)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_KB_ARTICLE_ARCHIVED,
            resource_type="support_knowledge_article",
            resource_id=str(article.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=SupportKnowledgeArticleSerializer(article).data, message="مقاله آرشیو شد."
        )


class SupportAdminKnowledgeArticleUseView(APIView):
    """Admin action to record article usage in support reply/context."""

    permission_classes = [IsSupportAdminUser]

    @extend_schema(
        operation_id="support_admin_knowledge_article_use",
        tags=[TAG_SUPPORT_TAXONOMY],
        request=SupportKnowledgeArticleUseInputSerializer,
        responses={201: KNOWLEDGE_ARTICLE_USE_RESPONSE, 404: SUPPORT_ERROR_RESPONSE},
    )
    def post(self, request: Request, article_id: int) -> CreatedResponse | ErrorResponse:
        """Record article usage for analytics and audit."""
        article = selectors.get_admin_knowledge_article_by_id(article_id=article_id)
        if article is None:
            return ErrorResponse(message="مقاله یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = SupportKnowledgeArticleUseInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = None
        ticket_number = serializer.validated_data.get("ticket_number")
        if ticket_number:
            ticket = selectors.get_admin_ticket_by_number(ticket_number=ticket_number)
            if ticket is None:
                return ErrorResponse(
                    message="تیکت یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
                )
        article_use = services.record_knowledge_article_use(
            article=article,
            user=request.user,
            ticket=ticket,
            context=serializer.validated_data.get("context", "reply"),
        )
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.SUPPORT_KB_ARTICLE_USED,
            resource_type="support_knowledge_article",
            resource_id=str(article.pk),
            extra_data={
                "ticket_number": ticket.ticket_number if ticket else "",
                "context": article_use.context,
            },
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=SupportKnowledgeArticleUseSerializer(article_use).data,
            message="استفاده از مقاله ثبت شد.",
        )
