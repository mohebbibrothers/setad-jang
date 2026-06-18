"""LMS C3 learning recommendation tests."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.lms.choices import CourseLevel, EnrollmentStatus
from apps.lms.selectors import (
    get_admin_learning_recommendation_overview,
    get_user_learning_recommendations,
)
from tests.factories.auth import AdminUserFactory, UserFactory
from tests.factories.lms import (
    EnrollmentFactory,
    LMSCategoryFactory,
    LMSUserSkillFactory,
    PublishedCourseFactory,
)

pytestmark = pytest.mark.django_db


def _jwt_client(user) -> APIClient:
    """Build JWT-authenticated API client."""
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


def test_learning_recommendations_rank_affinity_and_level_progression() -> None:
    """Recommendations should prefer same-category next-level courses and exclude enrolled courses."""
    user = UserFactory()
    category = LMSCategoryFactory(title="مهارت رسانه")
    enrolled = PublishedCourseFactory(category=category, level=CourseLevel.BEGINNER, title="مقدماتی رسانه")
    recommended = PublishedCourseFactory(
        category=category,
        level=CourseLevel.INTERMEDIATE,
        title="متوسط رسانه",
        enrollments_count=8,
    )
    unrelated = PublishedCourseFactory(level=CourseLevel.BEGINNER, title="نامرتبط")
    EnrollmentFactory(user=user, course=enrolled, status=EnrollmentStatus.COMPLETED, progress_percent=100)

    recommendations = get_user_learning_recommendations(user_id=user.pk, limit=5)

    assert recommendations[0]["course"] == recommended
    assert enrolled.pk not in [item["course"].pk for item in recommendations]
    assert unrelated in [item["course"] for item in recommendations]
    assert "category_affinity" in recommendations[0]["reason_codes"]
    assert "level_progression" in recommendations[0]["reason_codes"]


def test_learning_recommendations_use_skill_gap_reason() -> None:
    """Courses in categories without earned skills should include skill-gap reason."""
    user = UserFactory()
    completed_category = LMSCategoryFactory(title="تکمیل‌شده")
    gap_category = LMSCategoryFactory(title="نیازمند یادگیری")
    completed_course = PublishedCourseFactory(category=completed_category)
    gap_course = PublishedCourseFactory(category=gap_category)
    LMSUserSkillFactory(user=user, course=completed_course)

    recommendations = get_user_learning_recommendations(user_id=user.pk, limit=5)
    gap_item = next(item for item in recommendations if item["course"] == gap_course)

    assert "skill_gap_category" in gap_item["reason_codes"]


def test_user_learning_recommendation_endpoint_returns_ranked_payload() -> None:
    """Authenticated users should receive recommendation payloads."""
    user = UserFactory()
    category = LMSCategoryFactory(title="Endpoint Category")
    enrolled = PublishedCourseFactory(category=category, level=CourseLevel.BEGINNER)
    PublishedCourseFactory(category=category, level=CourseLevel.INTERMEDIATE, title="Endpoint Recommendation")
    EnrollmentFactory(user=user, course=enrolled, status=EnrollmentStatus.ACTIVE, progress_percent=60)
    client = _jwt_client(user)

    response = client.get(reverse("lms:user-learning-recommendations"), data={"limit": 3})

    assert response.status_code == status.HTTP_200_OK
    assert response.data["success"] is True
    assert response.data["data"]
    assert response.data["data"][0]["course"]["title"] == "Endpoint Recommendation"
    assert response.data["data"][0]["score"] > 0


def test_admin_learning_recommendation_overview_endpoint() -> None:
    """Admins should see recommendation readiness overview."""
    admin = AdminUserFactory()
    PublishedCourseFactory(is_featured=True, enrollments_count=5)
    PublishedCourseFactory(enrollments_count=0)
    client = _jwt_client(admin)

    response = client.get(reverse("lms:admin-recommendations-overview"), data={"limit": 5})
    overview = get_admin_learning_recommendation_overview(limit=5)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["success"] is True
    assert response.data["data"]["published_courses"] == overview["published_courses"]
    assert response.data["data"]["featured_courses"] >= 1
    assert response.data["data"]["cold_start_courses"] >= 1
