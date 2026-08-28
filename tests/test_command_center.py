"""Apex B4 unified admin command center tests."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.kindness_wall.choices import ListingStatus
from apps.kindness_wall.models import KindnessListingReport
from apps.madadkar.choices import PaymentStatus
from apps.madadkar.models import Payment
from apps.notifications.services import create_notification_event
from apps.support_desk.choices import TicketStatus
from apps.tabyin.choices import ContentOrigin, SubmissionStatus
from apps.tabyin.models import TabyinContent
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.kindness_wall import (
    KindnessCategoryFactory,
    KindnessUserFactory,
    PublishedNeedListingFactory,
)
from tests.factories.lms import CertificateFactory, EnrollmentFactory, PublishedCourseFactory
from tests.factories.madadkar import PaidParticipationFactory, PublishedCampaignFactory
from tests.factories.r4j import R4JBountyFactory, R4JCriminalPublishedFactory, R4JReportFactory
from tests.factories.support_desk import SupportTicketFactory

pytestmark = pytest.mark.django_db


def _client_for(user) -> APIClient:
    """Return authenticated API client."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_command_center_requires_admin() -> None:
    """Regular users must not access command center."""
    response = _client_for(UserFactory()).get(reverse("command_center:summary"))

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_command_center_returns_cross_app_operational_summary() -> None:
    """Admin command center must aggregate all important app queues."""
    support_ticket = SupportTicketFactory(status=TicketStatus.SUBMITTED, assigned_to=None)
    support_ticket.sla_breached_at = support_ticket.created_at
    support_ticket.save(update_fields=["sla_breached_at", "updated_at"])

    category = KindnessCategoryFactory()
    listing = PublishedNeedListingFactory(category=category)
    listing.status = ListingStatus.PENDING_REVIEW
    listing.save(update_fields=["status", "updated_at"])
    KindnessListingReport.objects.create(
        listing=listing, reported_by=KindnessUserFactory(), reason="other"
    )

    TabyinContent.objects.create(
        external_id="command-center-submission",
        origin=ContentOrigin.USER_SUBMITTED,
        submitted_by=UserFactory(),
        submission_status=SubmissionStatus.PENDING_REVIEW,
        title="ارسال کاربر",
    )

    criminal = R4JCriminalPublishedFactory()
    R4JReportFactory(criminal=criminal)
    R4JBountyFactory(criminal=criminal)

    campaign = PublishedCampaignFactory()
    participation = PaidParticipationFactory(campaign=campaign)
    Payment.objects.create(
        participation=participation,
        user=participation.user,
        amount=10_000,
        gateway_name="sandbox",
        authority="CMD",
        status=PaymentStatus.SUCCESS,
    )

    course = PublishedCourseFactory()
    EnrollmentFactory(course=course)
    CertificateFactory(course=course)

    create_notification_event(
        event_type="command.event", recipients=[UserFactory()], payload={"title": "Command"}
    )

    response = _client_for(AdminUserFactory()).get(reverse("command_center:summary"))

    assert response.status_code == status.HTTP_200_OK
    data = response.data["data"]
    assert data["support"]["open_tickets"] >= 1
    assert data["support"]["sla_breached_tickets"] >= 1
    assert data["kindness_wall"]["pending_listings"] >= 1
    assert data["kindness_wall"]["pending_reports"] >= 1
    assert data["tabyin"]["pending_user_submissions"] >= 1
    assert data["r4j"]["published_criminals"] >= 1
    assert data["madadkar"]["published_campaigns"] >= 1
    assert data["madadkar"]["successful_payments"] >= 1
    assert data["lms"]["published_courses"] >= 1
    assert data["notifications"]["pending_events"] >= 1
    assert "email" in data["providers"]
    assert "status" in data["health"]
    assert data["generated_at"]
